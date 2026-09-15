"""One long turn through the orchestrator: early reads become receipts mid-turn; the transcript keeps the bodies."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from copenet.core.harness import within_turn_receipts
from copenet.core.orchestrator import Orchestrator
from copenet.core.orchestrator.requests import ChatSendRequest
from copenet.core.sessions import SessionStore, TranscriptStore
from responses_fake import ScriptedResponsesProvider, tool_outputs


@pytest.mark.asyncio
async def test_old_reads_are_receipted_mid_turn_once_the_request_is_large(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(within_turn_receipts, "RECEIPT_TRIGGER_TOKENS", 1_500)
    monkeypatch.setattr(within_turn_receipts, "MIN_FREED_TOKENS", 200)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "big.py").write_text("".join(f"value_{i} = {i}  # padding padding padding\n" for i in range(1200)), encoding="utf-8")
    reads = [f'{{"tool_id": "files.read", "arguments": {{"path": "big.py", "start_line": {1 + 200 * i}, "end_line": {200 + 200 * i}}}}}' for i in range(6)]
    provider = ScriptedResponsesProvider(outputs=[*reads, "Read it all."])
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        sessions_dir=tmp_path,
        providers={provider.name: provider},
    )

    async def emit(payload: dict) -> None:
        return None

    result = await orchestrator.send_chat(
        ChatSendRequest(session_key="wt", message="Read big.py in six pieces", idempotency_key="run-1", provider=provider.name, task_prompt_id="full-access", workspace_root=str(workspace)),
        emit=emit,
    )
    assert result["status"] == "ok", result

    # the request for the final step: early reads are receipts, the last three are verbatim
    final_request = provider.messages[-1]
    outputs = [json.loads(item["output"]) for item in tool_outputs(final_request)]
    assert len(outputs) == 6
    receipted = [o for o in outputs if "elided" in json.dumps(o["body"])]
    verbatim = [o for o in outputs if "content" in o["body"]]
    # the answer is step 7, so keep-3 protects steps 5 and 6; steps 1-4 aged out
    assert len(receipted) == 4 and len(verbatim) == 2
    assert all("content" in o["body"] for o in outputs[-2:])
    assert all("of this turn" in o["body"]["elided"] for o in receipted)
    # a persisted body is pointed at by its artifact id, so one call brings it back
    assert any("artifact.read" in o["body"]["elided"] for o in receipted)

    # the trace recorded the pass; the durable transcript still has every body
    rows = [json.loads(line) for line in (tmp_path / "logs" / "runs" / "run-1.jsonl").read_text().splitlines() if line.strip()]
    passes = [row for row in rows if row.get("event") == "within_turn_receipts_applied"]
    assert passes and passes[0]["payload"]["itemsReceipted"] >= 1 and passes[0]["payload"]["freedTokens"] > 0
    history = orchestrator.history(session_key="wt")
    stored = [part["toolExecution"]["replayOutput"] for row in history if row["role"] == "assistant" for part in row["parts"] if part["kind"] == "tool_result"]
    assert len(stored) == 6 and all("value_" in text for text in stored)
