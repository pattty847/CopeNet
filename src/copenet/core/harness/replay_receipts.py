"""What an earlier turn's tool result looks like when it is replayed.

Every prior turn used to replay every tool body verbatim, so a session's
second coding turn started with the whole first turn's file reads and command
output in context, and when the budget finally tripped the trimmer dropped an
entire earlier turn — edits included — at once. The chart lane had already
solved this for itself by stubbing old chart bodies to a receipt.

This is the general rule:

- The most recent `VERBATIM_RECENT_TURNS` completed turns replay verbatim.
- Older turns replay successful `files.read`, `files.rg`, `shell.exec`, `web.*`
  and other read-only results as receipts: what was asked, the identifying facts
  (path, range, digest, exit code, match count, first lines), and a note that the
  body can be fetched again. One call recovers the exact content.
- `files.edit` / `files.write` results and any failed call replay verbatim at any
  age. Edits are the record of change; failures are the reason the next step
  happened. Neither is re-derivable from disk.
- Chart tool results keep the stub `_with_chart_references` already gives them.

Replayed outputs carry the same envelope the model saw live (`toolId`, `ok`,
`summary`, `error`, `body`), with the access-policy bookkeeping stripped from
allowed calls exactly as `ToolExecutionResult.to_model_payload` strips it.
"""

from __future__ import annotations

import json
from typing import Any

from copenet.core.tools.contracts import MODEL_HIDDEN_POLICY_FIELDS

# How many of the newest completed turns keep their tool bodies verbatim on replay.
VERBATIM_RECENT_TURNS = 1

# Results that are the record of what the agent changed. Never receipted.
MUTATION_TOOL_IDS = frozenset({"files.edit", "files.write"})

RECEIPT_MATCH_LIMIT = 5
RECEIPT_LINE_LIMIT = 3
RECEIPT_LINE_CHARS = 200


def is_verbatim(tool_execution: dict[str, Any]) -> bool:
    """A result that must never be reduced to a receipt, however old the turn."""
    tool_id = str(tool_execution.get("toolId") or "")
    if tool_id in MUTATION_TOOL_IDS or tool_id.startswith("market.chart."):
        return True
    return tool_execution.get("ok") is False


def parse_replay_body(tool_execution: dict[str, Any]) -> Any:
    """Return the stored model-facing body as data when it was JSON, else as text."""
    raw = tool_execution.get("replayOutput")
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    body = tool_execution.get("body")
    if body is not None:
        return body
    output = tool_execution.get("output")
    if output is not None:
        return output
    return str(tool_execution.get("summary") or "")


def slim_body(body: Any, *, ok: bool) -> Any:
    if not isinstance(body, dict) or not ok or body.get("policyDecision") not in (None, "allowed"):
        return body
    return {key: value for key, value in body.items() if key not in MODEL_HIDDEN_POLICY_FIELDS}


def _head_tail(text: str) -> dict[str, Any]:
    lines = [line[:RECEIPT_LINE_CHARS] for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return {}
    if len(lines) <= RECEIPT_LINE_LIMIT * 2:
        return {"lines": lines}
    return {
        "firstLines": lines[:RECEIPT_LINE_LIMIT],
        "lastLines": lines[-RECEIPT_LINE_LIMIT:],
        "lineCount": len(lines),
    }


def receipt_body(tool_execution: dict[str, Any], body: Any, *, turn_number: int | None, where: str | None = None) -> Any:
    """The identifying facts of an old result, with a pointer to the way back to the full body."""
    tool_id = str(tool_execution.get("toolId") or "")
    arguments = tool_execution.get("arguments") if isinstance(tool_execution.get("arguments"), dict) else {}
    data = body if isinstance(body, dict) else {}
    where = where or (f"turn {turn_number}" if turn_number else "an earlier turn")
    receipt: dict[str, Any] = {}

    if tool_id == "files.read":
        receipt["path"] = data.get("path") or arguments.get("path")
        if data.get("startLine") is not None:
            receipt["lines"] = f"{data.get('startLine')}-{data.get('endLine')} of {data.get('totalLines')}"
        elif data.get("totalLines") is not None:
            receipt["totalLines"] = data.get("totalLines")
        if data.get("digest"):
            receipt["digest"] = data["digest"]
        receipt["elided"] = f"file content read in {where} is not replayed; call files.read again if you need it"
    elif tool_id == "files.rg":
        receipt["pattern"] = arguments.get("pattern")
        receipt["path"] = arguments.get("path")
        receipt["totalMatches"] = data.get("totalMatches")
        matches = data.get("matches") if isinstance(data.get("matches"), list) else []
        receipt["matches"] = [f"{m.get('path')}:{m.get('line')}" for m in matches[:RECEIPT_MATCH_LIMIT] if isinstance(m, dict)]
        if len(matches) > RECEIPT_MATCH_LIMIT:
            receipt["matches"].append(f"… {len(matches) - RECEIPT_MATCH_LIMIT} more")
        receipt["elided"] = f"match text from {where} is not replayed; call files.rg again if you need it"
    elif tool_id == "shell.exec":
        receipt["command"] = data.get("command") or arguments.get("command")
        receipt["exitCode"] = data.get("exitCode")
        stdout = _head_tail(str(data.get("stdout") or ""))
        stderr = _head_tail(str(data.get("stderr") or ""))
        if stdout:
            receipt["stdout"] = stdout
        if stderr:
            receipt["stderr"] = stderr
        receipt["elided"] = (
            f"full output from {where} is not replayed "
            f"({len(str(data.get('stdout') or ''))} stdout chars, {len(str(data.get('stderr') or ''))} stderr chars); "
            "run the command again if you need it"
        )
    elif tool_id == "web.fetch":
        receipt["url"] = data.get("url") or arguments.get("url")
        if data.get("title"):
            receipt["title"] = data["title"]
        receipt["elided"] = f"page content from {where} is not replayed; call web.fetch again if you need it"
    elif tool_id == "web.search":
        receipt["query"] = data.get("query") or arguments.get("query")
        results = data.get("results") if isinstance(data.get("results"), list) else []
        receipt["resultCount"] = len(results) if results else data.get("resultCount")
        receipt["elided"] = f"results from {where} are not replayed; call web.search again if you need them"
    elif tool_id == "plan.write":
        return None
    else:
        for key in ("path", "target", "symbol", "query", "url"):
            if isinstance(data.get(key), str):
                receipt[key] = data[key]
        receipt["elided"] = f"result body from {where} is not replayed; call {tool_id} again if you need it"
    artifact_id = tool_execution.get("artifactId")
    if isinstance(artifact_id, str) and artifact_id and receipt is not None:
        receipt["elided"] += f"; the full body is saved as artifact {artifact_id} (artifact.read)"
    return receipt


def replay_output(tool_execution: dict[str, Any], *, receipt: bool, turn_number: int | None = None, where: str | None = None) -> str:
    """The `function_call_output` string for one stored tool result."""
    ok = tool_execution.get("ok") is not False
    body = parse_replay_body(tool_execution)
    verbatim = _envelope(tool_execution, slim_body(body, ok=ok))
    if not receipt or is_verbatim(tool_execution):
        return verbatim
    receipted = _envelope(tool_execution, receipt_body(tool_execution, body, turn_number=turn_number, where=where))
    # A receipt that is not smaller than the body it stands in for is pure loss:
    # a two-line command output stays as it was.
    return receipted if len(receipted) < len(verbatim) else verbatim


def _envelope(tool_execution: dict[str, Any], body: Any) -> str:
    envelope: dict[str, Any] = {
        "toolId": tool_execution.get("toolId"),
        "ok": tool_execution.get("ok") is not False,
        "summary": tool_execution.get("summary"),
        "body": body,
    }
    if tool_execution.get("error"):
        envelope["error"] = tool_execution["error"]
    if tool_execution.get("artifactId"):
        envelope["artifactId"] = tool_execution["artifactId"]
    return json.dumps(envelope, ensure_ascii=False)
