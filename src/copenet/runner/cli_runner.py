"""Async subprocess runner for CLI-backed providers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import subprocess
import sys
from typing import AsyncIterator, Sequence


@dataclass(frozen=True)
class RunnerEvent:
    """A single streamed output line from a process."""

    stream: str
    line: str


@dataclass(frozen=True)
class RunnerResult:
    """Final process completion result."""

    returncode: int
    stdout_tail: str
    stderr_tail: str


class CliRunner:
    """Small async runner with line streaming and abort/timeout support."""

    async def run(
        self,
        argv: Sequence[str],
        timeout_sec: float | None = None,
        abort_event: asyncio.Event | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> AsyncIterator[RunnerEvent | RunnerResult]:
        """Run a subprocess and stream events."""
        spawn_kwargs = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "cwd": cwd,
            "env": env,
        }
        if sys.platform == "win32":
            spawn_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        process = await asyncio.create_subprocess_exec(*argv, **spawn_kwargs)

        if process.stdout is None or process.stderr is None:
            raise RuntimeError("failed to create subprocess streams")

        stdout_tail: list[str] = []
        stderr_tail: list[str] = []
        tail_limit = 200

        queue: asyncio.Queue[RunnerEvent | tuple[str, None]] = asyncio.Queue()

        async def pump(stream_name: str, reader: asyncio.StreamReader) -> None:
            while True:
                line_bytes = await reader.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode(errors="replace").rstrip("\r\n")
                if stream_name == "stdout":
                    stdout_tail.append(line)
                    if len(stdout_tail) > tail_limit:
                        stdout_tail.pop(0)
                else:
                    stderr_tail.append(line)
                    if len(stderr_tail) > tail_limit:
                        stderr_tail.pop(0)
                await queue.put(RunnerEvent(stream=stream_name, line=line))
            await queue.put((stream_name, None))

        stdout_task = asyncio.create_task(pump("stdout", process.stdout))
        stderr_task = asyncio.create_task(pump("stderr", process.stderr))

        done_streams = 0
        wait_task = asyncio.create_task(process.wait())
        timeout_task = (
            asyncio.create_task(asyncio.sleep(timeout_sec)) if timeout_sec and timeout_sec > 0 else None
        )
        abort_task = asyncio.create_task(abort_event.wait()) if abort_event is not None else None

        try:
            while True:
                queue_task = asyncio.create_task(queue.get())
                watch_tasks = {queue_task, wait_task}
                if timeout_task is not None:
                    watch_tasks.add(timeout_task)
                if abort_task is not None:
                    watch_tasks.add(abort_task)

                done, _pending = await asyncio.wait(watch_tasks, return_when=asyncio.FIRST_COMPLETED)
                if queue_task in done:
                    item = queue_task.result()
                    if isinstance(item, tuple):
                        done_streams += 1
                    else:
                        yield item
                else:
                    queue_task.cancel()

                if timeout_task is not None and timeout_task in done:
                    process.kill()
                    await process.wait()
                    raise TimeoutError("CLI command timed out")

                if abort_task is not None and abort_task in done:
                    process.kill()
                    await process.wait()
                    raise RuntimeError("CLI command aborted")

                if wait_task in done and done_streams >= 2:
                    break
        finally:
            if timeout_task is not None:
                timeout_task.cancel()
            if abort_task is not None:
                abort_task.cancel()
            stdout_task.cancel()
            stderr_task.cancel()

        returncode = await process.wait()
        yield RunnerResult(
            returncode=returncode,
            stdout_tail="\n".join(stdout_tail),
            stderr_tail="\n".join(stderr_tail),
        )
