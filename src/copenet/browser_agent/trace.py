"""Trace recorder for deterministic browser-agent runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import uuid

from copenet.core.tracing import utc_now_iso

from .models import ActionResult, BrowserAction, PageState


@dataclass(frozen=True)
class BrowserTraceContext:
    task_id: str
    session_id: str


class BrowserTraceRecorder:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._root_dir.mkdir(parents=True, exist_ok=True)

    def create_context(self, task_id: str | None = None, session_id: str | None = None) -> BrowserTraceContext:
        return BrowserTraceContext(task_id=task_id or f"browser-task-{uuid.uuid4().hex[:8]}", session_id=session_id or uuid.uuid4().hex)

    def trace_path(self, ctx: BrowserTraceContext) -> Path:
        return self._root_dir / f"{ctx.task_id}.jsonl"

    def record(
        self,
        ctx: BrowserTraceContext,
        *,
        step_index: int,
        task: str,
        state_before: PageState,
        action: BrowserAction,
        validation_result: str,
        result: ActionResult,
        state_after: PageState | None = None,
        error: str | None = None,
        stop_reason: str | None = None,
    ) -> Path:
        path = self.trace_path(ctx)
        payload: dict[str, Any] = {
            "timestamp": utc_now_iso(),
            "task_id": ctx.task_id,
            "session_id": ctx.session_id,
            "step_index": step_index,
            "task": task,
            "url_before": state_before.url,
            "page_title": state_before.title,
            "observed_elements_count": len(state_before.elements),
            "selected_action": action.action,
            "action_args": action.to_dict(),
            "validation_result": validation_result,
            "execution_result": result.to_dict(),
            "page_change": result.page_change.to_dict() if result.page_change is not None else None,
            "url_after": (state_after.url if state_after is not None else result.url_after),
            "screenshot_path": result.screenshot_path,
            "error": error or result.error,
            "stop_reason": stop_reason,
        }
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return path
