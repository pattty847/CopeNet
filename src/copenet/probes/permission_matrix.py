"""Direct permission probes for the CopeNet tool runtime."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Any
import uuid

from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.core.tools import ToolExecutionContext, ToolExecutionRequest, ToolRegistry, policy_for_task_mode


@dataclass(frozen=True)
class PermissionProbeCase:
    """One direct tool policy probe."""

    name: str
    tool_id: str
    arguments: dict[str, Any]
    expected_by_mode: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class PermissionProbeRow:
    """Observed result for one probe case in one task mode."""

    task_mode: str
    probe: str
    tool_id: str
    ok: bool
    expected_ok: bool
    passed: bool
    policy_decision: str
    expected_policy_decision: str | None
    summary: str
    error: str | None
    stdout_preview: str

    def to_json(self) -> dict[str, Any]:
        return {
            "task_mode": self.task_mode,
            "probe": self.probe,
            "tool_id": self.tool_id,
            "ok": self.ok,
            "expected_ok": self.expected_ok,
            "passed": self.passed,
            "policy_decision": self.policy_decision,
            "expected_policy_decision": self.expected_policy_decision,
            "summary": self.summary,
            "error": self.error,
            "stdout_preview": self.stdout_preview,
        }


def build_permission_probe_cases() -> list[PermissionProbeCase]:
    """Return objective checks for read, write, shell syntax, and approval gates."""
    return [
        PermissionProbeCase(
            name="safe_shell_read",
            tool_id="shell.exec",
            arguments={"command": "pwd"},
            expected_by_mode={
                "none": {"ok": True, "policyDecision": "allowed"},
                "full-access": {"ok": True, "policyDecision": "allowed"},
            },
        ),
        PermissionProbeCase(
            name="shell_syntax_pipe",
            tool_id="shell.exec",
            arguments={"command": "printf hi | tr a-z A-Z"},
            expected_by_mode={
                "none": {"ok": False, "policyDecision": "unsafe_unknown"},
                "full-access": {"ok": True, "policyDecision": "allowed", "stdout": "HI"},
            },
        ),
        PermissionProbeCase(
            name="repo_write_tool",
            tool_id="files.write",
            arguments={"path": ".copenet-permission-probe.txt", "content": "permission probe\n"},
            expected_by_mode={
                "none": {"ok": False, "policyDecision": "write_blocked"},
                "full-access": {"ok": True, "policyDecision": "allowed"},
            },
        ),
        PermissionProbeCase(
            name="high_risk_shell_approval",
            tool_id="shell.exec",
            arguments={"command": "sudo reboot"},
            expected_by_mode={
                "none": {"ok": False, "policyDecision": "unsafe_unknown"},
                "full-access": {"ok": False, "policyDecision": "approval_required"},
            },
        ),
        PermissionProbeCase(
            name="repo_mutation_approval",
            tool_id="shell.exec",
            arguments={"command": "git reset --hard"},
            expected_by_mode={
                "none": {"ok": False, "policyDecision": "write_blocked"},
                "full-access": {"ok": False, "policyDecision": "approval_required"},
            },
        ),
    ]


def _context(workdir: Path, *, task_mode: str) -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=workdir,
        session_workspace_root=workdir,
        session_key=f"permission-probe-{uuid.uuid4().hex[:8]}",
        provider_name="permission-probe",
        model=None,
        session_store=SessionStore(path=workdir / ".probe-session-index.json"),
        transcript_store=TranscriptStore(root_dir=workdir / ".probe-history"),
        providers={},
        policy=policy_for_task_mode(None if task_mode == "none" else task_mode),
        trace=None,
    )


async def run_permission_matrix(
    *,
    task_modes: list[str] | None = None,
    workspace: Path | None = None,
) -> list[PermissionProbeRow]:
    """Run direct tool permission probes without involving an LLM."""
    modes = task_modes or ["none", "full-access"]
    cases = build_permission_probe_cases()
    registry = ToolRegistry()
    owned_temp: tempfile.TemporaryDirectory[str] | None = None
    if workspace is None:
        owned_temp = tempfile.TemporaryDirectory(prefix="copenet-permission-probe-")
        workspace = Path(owned_temp.name)
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        rows: list[PermissionProbeRow] = []
        for mode in modes:
            mode_workspace = workspace / mode.replace("/", "_")
            mode_workspace.mkdir(parents=True, exist_ok=True)
            context = _context(mode_workspace, task_mode=mode)
            for case in cases:
                result = await registry.execute(
                    ToolExecutionRequest(tool_id=case.tool_id, arguments=dict(case.arguments)),
                    context,
                )
                expected = case.expected_by_mode.get(mode, {})
                output = result.output if isinstance(result.output, dict) else {}
                policy_decision = str(output.get("policyDecision") or "")
                stdout_preview = str(output.get("stdout") or "")[:120]
                expected_stdout = expected.get("stdout")
                passed = (
                    result.ok is bool(expected.get("ok"))
                    and (expected.get("policyDecision") is None or policy_decision == expected.get("policyDecision"))
                    and (expected_stdout is None or stdout_preview == expected_stdout)
                )
                rows.append(
                    PermissionProbeRow(
                        task_mode=mode,
                        probe=case.name,
                        tool_id=case.tool_id,
                        ok=result.ok,
                        expected_ok=bool(expected.get("ok")),
                        passed=passed,
                        policy_decision=policy_decision,
                        expected_policy_decision=expected.get("policyDecision"),
                        summary=result.summary,
                        error=result.error,
                        stdout_preview=stdout_preview,
                    )
                )
        return rows
    finally:
        if owned_temp is not None:
            await asyncio.to_thread(owned_temp.cleanup)

