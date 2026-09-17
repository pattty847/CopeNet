"""Persistent, harness-owned terminal sessions for one active agent run.

This is intentionally not a tmux wrapper.  The harness owns one shell process
and its process group, so it can retain ordinary shell state while still
enforcing run ownership, output bounds, interruption, and cleanup.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
import os
from pathlib import Path
import pty
import secrets
import select
import signal
import termios
import time
from typing import Any

from copenet.core.tools.contracts import ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult

from ._shared import _clip_with_marker
from .shell import approval_required_result


DESCRIPTORS = [
    ToolDescriptor(
        id="terminal.start",
        name="Start Terminal",
        description=(
            "Start the run-owned persistent terminal in the current workdir. "
            "Call this before terminal.exec. Shell state such as cd and export lasts only until terminal.close or run cleanup."
        ),
        category="shell-write",
        safety_level="guarded",
        capabilities=["terminal", "persistent-session"],
        evidence_role="verification",
        side_effect="external",
    ),
    ToolDescriptor(
        id="terminal.exec",
        name="Execute Terminal Command",
        description=(
            "Run a command in the run-owned persistent terminal. The command uses the terminal's current directory and environment. "
            "Start it first with terminal.start."
        ),
        category="shell-write",
        safety_level="guarded",
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 600},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
        capabilities=["terminal", "persistent-session", "shell"],
        evidence_role="verification",
        side_effect="external",
    ),
    ToolDescriptor(
        id="terminal.read",
        name="Read Terminal Output",
        description=(
            "Read output produced since the previous terminal call, optionally waiting briefly for a background process. "
            "Use this after starting a server or other background command."
        ),
        category="shell-write",
        safety_level="guarded",
        input_schema={
            "type": "object",
            "properties": {"wait_seconds": {"type": "integer", "minimum": 0, "maximum": 30}},
            "additionalProperties": False,
        },
        capabilities=["terminal", "persistent-session", "logs"],
        evidence_role="verification",
        side_effect="external",
    ),
    ToolDescriptor(
        id="terminal.interrupt",
        name="Interrupt Terminal",
        description="Send Ctrl-C to the persistent terminal's process group to stop foreground work.",
        category="shell-write",
        safety_level="guarded",
        capabilities=["terminal", "interrupt"],
        evidence_role="verification",
        side_effect="external",
    ),
    ToolDescriptor(
        id="terminal.close",
        name="Close Terminal",
        description="Close the persistent terminal and terminate its owned process group. It is also closed automatically when the run ends.",
        category="shell-write",
        safety_level="guarded",
        capabilities=["terminal", "cleanup"],
        evidence_role="verification",
        side_effect="external",
    ),
]


class PersistentTerminal:
    """A single POSIX shell and PTY owned by one run's tool context."""

    def __init__(self, *, workdir: Path) -> None:
        self.workdir = workdir
        self.id = f"term_{secrets.token_hex(6)}"
        self._master_fd: int | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._pending = ""
        self._lock = asyncio.Lock()

    @property
    def active(self) -> bool:
        return self._process is not None and self._process.returncode is None and self._master_fd is not None

    async def start(self) -> None:
        if self.active:
            return
        if os.name != "posix":
            raise RuntimeError("persistent terminals require a POSIX runtime")
        master_fd, slave_fd = pty.openpty()
        # Commands and their wrapper must not be echoed back as terminal output.
        attributes = termios.tcgetattr(slave_fd)
        attributes[3] &= ~termios.ECHO
        termios.tcsetattr(slave_fd, termios.TCSANOW, attributes)
        shell = os.environ.get("SHELL") or "/bin/bash"
        shell_name = Path(shell).name
        shell_argv = [shell, "-i"]
        if shell_name == "bash":
            shell_argv = [shell, "--noprofile", "--norc", "-i"]
        elif shell_name == "zsh":
            shell_argv = [shell, "-f", "-i"]
        environment = dict(os.environ)
        environment.update({"PS1": "", "PROMPT_COMMAND": "", "TERM": "dumb"})
        try:
            self._process = await asyncio.create_subprocess_exec(
                *shell_argv,
                cwd=str(self.workdir),
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=environment,
                start_new_session=True,
            )
        finally:
            os.close(slave_fd)
        self._master_fd = master_fd
        await self._drain_available()

    async def execute(self, command: str, *, timeout_seconds: int, output_limit: int) -> tuple[int, str]:
        if not self.active:
            raise RuntimeError("No active terminal. Call terminal.start first.")
        marker = f"__COPENET_TERMINAL_DONE_{secrets.token_hex(16)}__"
        wrapped = f"\n{command}\n__copenet_status=$?; printf '\\n{marker}%s\\n' \"$__copenet_status\"\n"
        async with self._lock:
            self._write(wrapped)
            try:
                status, output = await asyncio.wait_for(self._read_until(marker), timeout=timeout_seconds)
            except TimeoutError as exc:
                raise RuntimeError(f"terminal command timed out after {timeout_seconds}s; use terminal.interrupt to stop it") from exc
        return status, _clip_with_marker(output, output_limit, "terminal output")

    async def read(self, *, wait_seconds: int, output_limit: int) -> str:
        if not self.active:
            raise RuntimeError("No active terminal. Call terminal.start first.")
        async with self._lock:
            if wait_seconds and not self._pending:
                await self._read_one(timeout_seconds=wait_seconds)
            await self._drain_available()
            output, self._pending = self._pending, ""
        return _clip_with_marker(output, output_limit, "terminal output")

    async def interrupt(self) -> None:
        if not self.active:
            raise RuntimeError("No active terminal. Call terminal.start first.")
        assert self._process is not None
        try:
            os.killpg(self._process.pid, signal.SIGINT)
        except ProcessLookupError:
            return

    async def close(self) -> None:
        process, master_fd = self._process, self._master_fd
        self._process = None
        self._master_fd = None
        if process is not None and process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.wait()
        if master_fd is not None:
            try:
                os.close(master_fd)
            except OSError:
                pass

    def _write(self, text: str) -> None:
        if self._master_fd is None:
            raise RuntimeError("terminal is closed")
        os.write(self._master_fd, text.encode("utf-8"))

    async def _read_until(self, marker: str) -> tuple[int, str]:
        while True:
            marker_index = self._pending.find(marker)
            if marker_index >= 0:
                tail = self._pending[marker_index + len(marker) :]
                line_end = tail.find("\n")
                if line_end >= 0:
                    status_text = tail[:line_end].strip("\r")
                    if status_text.isdigit():
                        output = self._pending[:marker_index].rstrip("\r\n")
                        self._pending = tail[line_end + 1 :]
                        return int(status_text), output
            await self._read_one(timeout_seconds=1)

    async def _drain_available(self) -> None:
        while await self._read_one(timeout_seconds=0):
            pass

    async def _read_one(self, *, timeout_seconds: int) -> bool:
        if self._master_fd is None:
            return False

        def read_once() -> bytes:
            ready, _, _ = select.select([self._master_fd], [], [], timeout_seconds)
            if not ready:
                return b""
            try:
                return os.read(self._master_fd, 8192)
            except OSError:
                return b""

        payload = await asyncio.to_thread(read_once)
        if not payload:
            return False
        self._pending += payload.decode("utf-8", errors="replace")
        return True


def _terminal(context: ToolExecutionContext) -> PersistentTerminal | None:
    value = context.ephemeral.get("persistent_terminal")
    return value if isinstance(value, PersistentTerminal) else None


def _output(context: ToolExecutionContext, terminal: PersistentTerminal, **values: Any) -> dict[str, Any]:
    return {
        "terminalId": terminal.id,
        "workspaceRoot": str(context.session_workspace_root),
        "target": f"terminal:{terminal.id}",
        "scope": "inside_workspace",
        "accessAction": "write",
        "policyDecision": "allowed",
        "policySummary": "Run-owned persistent terminal executed under Full Access.",
        **values,
    }


def _trace(context: ToolExecutionContext, event: str, payload: dict[str, Any]) -> None:
    if context.trace is not None:
        context.trace(event, payload)


async def terminal_start(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    del request
    terminal = _terminal(context)
    reused = terminal is not None and terminal.active
    if terminal is None:
        terminal = PersistentTerminal(workdir=Path(context.workdir))
        context.ephemeral["persistent_terminal"] = terminal
    await terminal.start()
    _trace(context, "terminal_session_started", {"terminalId": terminal.id, "reused": reused})
    return ToolExecutionResult(
        tool_id="terminal.start",
        ok=True,
        summary="Persistent terminal ready." if not reused else "Persistent terminal already active.",
        output=_output(context, terminal, state="active", reused=reused),
    )


async def terminal_exec(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    terminal = _terminal(context)
    if terminal is None:
        return ToolExecutionResult(tool_id=request.tool_id, ok=False, summary="No persistent terminal is active.", error="Call terminal.start first.")
    command = str(request.arguments.get("command") or "").strip()
    if not command:
        raise ValueError("command is required")
    approval = approval_required_result(command, context)
    if approval is not None:
        return replace(approval, tool_id=request.tool_id)
    requested_timeout = int(request.arguments.get("timeout_seconds") or context.policy.shell_timeout_sec)
    timeout_seconds = min(max(requested_timeout, 1), 600)
    status, output = await terminal.execute(
        command,
        timeout_seconds=timeout_seconds,
        output_limit=context.policy.shell_output_limit,
    )
    body = _output(context, terminal, command=command, exitCode=status, output=output)
    _trace(context, "terminal_command_completed", {"terminalId": terminal.id, "exitCode": status, "commandChars": len(command)})
    if status:
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=False,
            summary=f"Terminal command failed with exit {status}.",
            error=output or f"command failed with exit {status}",
            output=body,
        )
    return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary="Terminal command completed.", output=body)


async def terminal_read(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    terminal = _terminal(context)
    if terminal is None:
        return ToolExecutionResult(tool_id=request.tool_id, ok=False, summary="No persistent terminal is active.", error="Call terminal.start first.")
    wait_seconds = min(max(int(request.arguments.get("wait_seconds") or 0), 0), 30)
    output = await terminal.read(wait_seconds=wait_seconds, output_limit=context.policy.shell_output_limit)
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary="Read persistent terminal output." if output else "No new terminal output.",
        output=_output(context, terminal, output=output, waitSeconds=wait_seconds),
    )


async def terminal_interrupt(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    terminal = _terminal(context)
    if terminal is None:
        return ToolExecutionResult(tool_id=request.tool_id, ok=False, summary="No persistent terminal is active.", error="Call terminal.start first.")
    await terminal.interrupt()
    _trace(context, "terminal_session_interrupted", {"terminalId": terminal.id})
    return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary="Sent Ctrl-C to persistent terminal.", output=_output(context, terminal))


async def terminal_close(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    terminal = _terminal(context)
    if terminal is None:
        return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary="No persistent terminal was active.")
    await terminal.close()
    context.ephemeral.pop("persistent_terminal", None)
    _trace(context, "terminal_session_closed", {"terminalId": terminal.id, "reason": "tool"})
    return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary="Closed persistent terminal.", output=_output(context, terminal, state="closed"))


async def close_terminal_for_run(context: ToolExecutionContext) -> None:
    """Close the run-owned terminal even if the model never requested close."""
    terminal = _terminal(context)
    if terminal is None:
        return
    await terminal.close()
    context.ephemeral.pop("persistent_terminal", None)
    _trace(context, "terminal_session_closed", {"terminalId": terminal.id, "reason": "run_finished"})


HANDLERS = {
    "terminal.start": terminal_start,
    "terminal.exec": terminal_exec,
    "terminal.read": terminal_read,
    "terminal.interrupt": terminal_interrupt,
    "terminal.close": terminal_close,
}
