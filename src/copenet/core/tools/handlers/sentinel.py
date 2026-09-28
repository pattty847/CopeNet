"""Model-facing observation and operator-approved control of Sentinel's GUI."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from copenet.core.tools.barricade import approval_key
from copenet.core.tools.contracts import ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult
from copenet.core.tools.result_limits import model_facing_result_char_limit

from .sentinel_client import SentinelApiError, sentinel_request


_INTEGER = {"type": "integer", "minimum": 0}
_SYMBOL = {"type": "string", "pattern": "^[A-Za-z0-9]{2,20}-[A-Za-z0-9]{2,20}$"}
_LAYERS = ("heatmap", "candles", "footprint", "tpo", "volumeProfile")
_VIEWPORT_PROPERTIES = {
    "startMs": _INTEGER, "endMs": _INTEGER,
    "priceMin": {"type": "number", "exclusiveMinimum": 0},
    "priceMax": {"type": "number", "exclusiveMinimum": 0},
    "followLive": {"type": "boolean"},
}


def _schema(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


DESCRIPTORS = [
    ToolDescriptor("sentinel.state", "Sentinel State", "Read the local Sentinel GUI connection, configuration, layers and source freshness.", "context", _schema({"symbol": _SYMBOL}), side_effect="read", evidence_role="grounding"),
    ToolDescriptor("sentinel.viewport", "Sentinel Viewport", "Read Sentinel's active chart bounds, timeframe, follow mode and viewport version.", "context", _schema({"symbol": _SYMBOL}), side_effect="read", evidence_role="grounding"),
    ToolDescriptor("sentinel.candles", "Sentinel Candles", "Read locally held Sentinel candles in a half-open UTC millisecond interval; no history is fetched.", "context", _schema({"startMs": _INTEGER, "endMs": _INTEGER, "timeframeMs": {"type": "integer", "minimum": 1}, "limit": {"type": "integer", "minimum": 1, "maximum": 2000}, "symbol": _SYMBOL}, ["startMs", "endMs", "timeframeMs"]), side_effect="read", evidence_role="grounding"),
    ToolDescriptor("sentinel.book", "Sentinel Book", "Read Sentinel's locally held order book levels and receive time; prices are dense-book buckets.", "context", _schema({"levels": {"type": "integer", "minimum": 1, "maximum": 200}, "symbol": _SYMBOL}), side_effect="read", evidence_role="grounding"),
    ToolDescriptor("sentinel.trades", "Sentinel Trades", "Read Sentinel's receive-time tape and full-window trade summary.", "context", _schema({"windowMs": {"type": "integer", "minimum": 1, "maximum": 900000}, "limit": {"type": "integer", "minimum": 1, "maximum": 1000}, "symbol": _SYMBOL}), side_effect="read", evidence_role="grounding"),
    ToolDescriptor("sentinel.walls", "Sentinel Heatmap Walls", "Read ranked price-level walls from Sentinel's loaded recording heatmap; sizes are aggregated resting cells, not individual orders.", "context", _schema({"startMs": _INTEGER, "endMs": _INTEGER, "priceMin": {"type": "number", "exclusiveMinimum": 0}, "priceMax": {"type": "number", "exclusiveMinimum": 0}, "minQty": {"type": "number", "minimum": 0}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}, "symbol": _SYMBOL}), side_effect="read", evidence_role="grounding"),
    ToolDescriptor("sentinel.screenshot", "Sentinel Screenshot", "Save a screenshot in Sentinel and return its PNG path and rendered frame metadata; Sentinel owns the path.", "context", _schema({"name": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,60}$"}, "target": {"type": "string", "enum": ["main", "heatmap", "lab"]}, "afterOperation": {"type": "string"}, "waitMs": {"type": "integer", "minimum": 0, "maximum": 5000}}), side_effect="read", evidence_role="grounding"),
    ToolDescriptor("sentinel.view.set", "Set Sentinel View", "Change the owner's visible Sentinel symbol, timeframe, viewport or layers; each exact call requires operator approval. Wait for the rendered frame before reporting completion, with an optional guarded screenshot.", "context", _schema({
        "symbol": _SYMBOL,
        "heatmapTimeframeMs": {"type": "integer", "minimum": 1},
        "candleTimeframeMs": {"type": "integer", "minimum": 1},
        "viewport": _schema(_VIEWPORT_PROPERTIES),
        "layers": _schema({key: {"type": "boolean"} for key in _LAYERS}),
        "waitMs": {"type": "integer", "minimum": 0, "maximum": 5000},
        "screenshot": {"type": "boolean"},
        "screenshotName": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,60}$"},
        "screenshotTarget": {"type": "string", "enum": ["main", "heatmap", "lab"]},
    }), safety_level="guarded", side_effect="write", requires_confirmation=True, evidence_role="mutation"),
]


def _int_argument(args: dict, name: str, default: int | None, maximum: int | None = None, minimum: int = 0) -> int:
    value = args.get(name, default)
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        bound = f"{minimum}–{maximum}" if maximum is not None else f"at least {minimum}"
        raise ValueError(f"{name} must be an integer {bound}")
    return value


def _number_argument(args: dict, name: str, minimum: float, positive: bool = False) -> int | float:
    value = args[name]
    if type(value) not in {int, float} or not -math.inf < value < math.inf or value < minimum or (positive and value == minimum):
        bound = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be finite and {bound}")
    return value


def _read_params(request: ToolExecutionRequest) -> tuple[str, dict]:
    args = request.arguments
    symbol_params = {}
    if "symbol" in args:
        symbol = args["symbol"]
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z0-9]{2,20}-[A-Za-z0-9]{2,20}", symbol):
            raise ValueError("symbol must be BASE-QUOTE with 2–20 alphanumeric characters per side")
        symbol_params["symbol"] = symbol.upper()
    if request.tool_id == "sentinel.state":
        return "/api/v1/state", symbol_params
    if request.tool_id == "sentinel.viewport":
        return "/api/v1/viewport", symbol_params
    if request.tool_id == "sentinel.candles":
        start = _int_argument(args, "startMs", None)
        end = _int_argument(args, "endMs", None)
        timeframe = _int_argument(args, "timeframeMs", None)
        if end <= start or timeframe == 0:
            raise ValueError("candles require startMs < endMs and positive timeframeMs")
        return "/api/v1/candles", {**symbol_params, "startMs": start, "endMs": end, "timeframeMs": timeframe, "limit": _int_argument(args, "limit", 500, 2000, 1)}
    if request.tool_id == "sentinel.book":
        return "/api/v1/book", {**symbol_params, "levels": _int_argument(args, "levels", 20, 200, 1)}
    if request.tool_id == "sentinel.walls":
        if ("startMs" in args) != ("endMs" in args) or ("priceMin" in args) != ("priceMax" in args):
            raise ValueError("walls time and price bounds must be paired")
        params = {**symbol_params, "limit": _int_argument(args, "limit", 20, 100, 1)}
        if "startMs" in args:
            params.update(startMs=_int_argument(args, "startMs", None), endMs=_int_argument(args, "endMs", None))
            if params["endMs"] <= params["startMs"]:
                raise ValueError("walls endMs must exceed startMs")
        if "priceMin" in args:
            params.update(priceMin=_number_argument(args, "priceMin", 0, positive=True),
                          priceMax=_number_argument(args, "priceMax", 0, positive=True))
            if params["priceMax"] <= params["priceMin"]:
                raise ValueError("walls priceMax must exceed priceMin")
        params["minQty"] = _number_argument(args, "minQty", 0) if "minQty" in args else 0
        return "/api/v1/heatmap/walls", params
    return "/api/v1/trades", {**symbol_params, "windowMs": _int_argument(args, "windowMs", 60000, 900000, 1), "limit": _int_argument(args, "limit", 100, 1000, 1)}


def _model_body(envelope: dict, tool_id: str) -> str:
    data = dict(envelope["data"])
    rows: list | None = None
    field = {"sentinel.candles": "bars", "sentinel.trades": "trades"}.get(tool_id)
    if field:
        rows = data.pop(field, [])
        data[f"{field}Count"] = len(rows)
        if rows:
            data["first"] = rows[0]
            data["last"] = rows[-1]
    elif tool_id == "sentinel.book":
        for side in ("bids", "asks"):
            levels = data.pop(side, [])
            data[f"{side}Count"] = len(levels)
            data[side] = levels[:10]
        data["shownLevelsPerSide"] = 10
    elif tool_id == "sentinel.walls":
        walls = data.pop("walls", [])
        data["wallCount"] = len(walls)
        data["interpretation"] = "Each row is a price level with aggregated resting size per cell, not individual orders."
        header = "rank | side | price range | peak qty | mean qty | persistence | notional"
        rows = [f"{rank} | {wall['side']} | {wall['priceLow']:g}–{wall['priceHigh']:g} | {wall['qty']:g} | {wall['meanQty']:g} | {wall['columns']}/{data['recordedColumns']} | {wall['notional']:g}" for rank, wall in enumerate(walls, 1)]
        data["rankedTable"] = "\n".join([header, *rows])
        data["shownWalls"] = len(rows)
        while rows and len(json.dumps(json.dumps({"meta": envelope["meta"], "data": data}, ensure_ascii=False, separators=(",", ":")), ensure_ascii=False)) > model_facing_result_char_limit():
            rows.pop()
            data["rankedTable"] = "\n".join([header, *rows])
            data["shownWalls"] = len(rows)
    body = {"meta": envelope["meta"], "data": data}
    limit = model_facing_result_char_limit()
    rendered = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    if len(json.dumps(rendered, ensure_ascii=False)) <= limit:
        return rendered
    # Preserve evidence metadata even with unusually small configured result budgets.
    body["data"] = {"summary": "Payload exceeds model result budget; inspect the saved tool output artifact.", "keys": list(envelope["data"])}
    rendered = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    if len(json.dumps(rendered, ensure_ascii=False)) > limit:
        body["data"] = {"summary": "Payload exceeds model result budget."}
        rendered = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    return rendered


def _control_model_body(output: dict) -> str:
    body = {"meta": output["meta"], "frame": output["frame"],
            "operations": [{"kind": item["kind"], **item["operation"]["data"]} for item in output["operations"]]}
    if "screenshot" in output:
        body["screenshot"] = output["screenshot"]
    rendered = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    if len(json.dumps(rendered, ensure_ascii=False)) > model_facing_result_char_limit():
        body = {"meta": output["meta"], "frame": output["frame"],
                "operationCount": len(output["operations"]), "screenshot": output.get("screenshot")}
        rendered = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    return rendered


def _screenshot_model_body(screenshot: dict) -> str:
    rendered = json.dumps(screenshot, ensure_ascii=False, separators=(",", ":"))
    limit = model_facing_result_char_limit()
    if len(json.dumps(rendered, ensure_ascii=False)) > limit:
        screenshot = {**screenshot, "path": screenshot["path"][: max(limit // 4, 1)], "pathTruncatedForModel": True}
        rendered = json.dumps(screenshot, ensure_ascii=False, separators=(",", ":"))
    return rendered


def _result(request: ToolExecutionRequest, envelope: dict, summary: str) -> ToolExecutionResult:
    return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary=summary, output=envelope,
                               model_body=_model_body(envelope, request.tool_id))


def _error(request: ToolExecutionRequest, error: SentinelApiError | ValueError) -> ToolExecutionResult:
    code = error.code if isinstance(error, SentinelApiError) else "invalid_arguments"
    message = str(error)
    summary = f"Sentinel: {code}"
    if request.tool_id == "sentinel.walls" and code == "recording_required":
        message = f"{message} Switch Sentinel heatmap.source to recording."
        summary = "Sentinel walls require recording; switch Sentinel heatmap.source to recording."
    return ToolExecutionResult(tool_id=request.tool_id, ok=False, summary=summary,
                               error=message, output={"code": code, "message": message})


async def read_sentinel(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    try:
        if request.tool_id == "sentinel.screenshot":
            args = request.arguments
            name = args.get("name", "agent-review")
            target = args.get("target", "main")
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", name) or target not in {"main", "heatmap", "lab"}:
                raise ValueError("screenshot requires a safe name and target main, heatmap or lab")
            params: dict[str, Any] = {"name": name, "target": target}
            if "afterOperation" in args:
                operation = args["afterOperation"]
                if not isinstance(operation, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", operation):
                    raise ValueError("afterOperation must be a Sentinel operation id")
                params["afterOperation"] = operation
                params["waitMs"] = _int_argument(args, "waitMs", 5000, 5000)
            screenshot = await sentinel_request("GET", "/api/v1/screenshot", params=params,
                                                 timeout=6.0 if "afterOperation" in args else 3.0, screenshot=True)
            return ToolExecutionResult(tool_id=request.tool_id, ok=True,
                                       summary=f"Sentinel screenshot saved at {screenshot['path']}",
                                       output=screenshot, model_body=_screenshot_model_body(screenshot))
        path, params = _read_params(request)
        envelope = await sentinel_request("GET", path, params=params)
        summary = f"Sentinel {request.tool_id.removeprefix('sentinel.')} observed"
        return _result(request, envelope, summary)
    except (SentinelApiError, ValueError) as exc:
        return _error(request, exc)


def _controls(args: dict) -> list[tuple[str, dict]]:
    controls: list[tuple[str, dict]] = []
    if "symbol" in args:
        symbol = args["symbol"]
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z0-9]{2,20}-[A-Za-z0-9]{2,20}", symbol):
            raise ValueError("symbol must be BASE-QUOTE with 2–20 alphanumeric characters per side")
        controls.append(("symbol", {"symbol": symbol.upper()}))
    timeframe = {key: args[key] for key in ("heatmapTimeframeMs", "candleTimeframeMs") if key in args}
    if timeframe:
        for key in timeframe:
            if _int_argument(args, key, None) == 0:
                raise ValueError(f"{key} must be positive")
        if len(set(timeframe.values())) > 1:
            raise ValueError("Sentinel v1 requires equal heatmap and candle timeframes")
        controls.append(("timeframe", timeframe))
    if "viewport" in args:
        viewport = args["viewport"]
        if not isinstance(viewport, dict) or not viewport or set(viewport) - set(_VIEWPORT_PROPERTIES):
            raise ValueError("viewport must contain supported bounds or followLive")
        if ("startMs" in viewport) != ("endMs" in viewport) or ("priceMin" in viewport) != ("priceMax" in viewport):
            raise ValueError("viewport time and price bounds must be paired")
        for key in ("startMs", "endMs"):
            if key in viewport:
                _int_argument(viewport, key, None)
        for key in ("priceMin", "priceMax"):
            if key in viewport and (type(viewport[key]) not in {float, int} or not 0 < viewport[key] < float("inf")):
                raise ValueError(f"{key} must be finite and positive")
        if "startMs" in viewport and viewport["endMs"] <= viewport["startMs"]:
            raise ValueError("viewport endMs must exceed startMs")
        if "priceMin" in viewport and viewport["priceMax"] <= viewport["priceMin"]:
            raise ValueError("viewport priceMax must exceed priceMin")
        if "followLive" in viewport and type(viewport["followLive"]) is not bool:
            raise ValueError("followLive must be boolean")
        if viewport.get("followLive") is True and any(key in viewport for key in ("startMs", "endMs", "priceMin", "priceMax")):
            raise ValueError("followLive:true cannot be combined with explicit viewport bounds")
        controls.append(("viewport", viewport))
    if "layers" in args:
        layers = args["layers"]
        if not isinstance(layers, dict) or not layers or set(layers) - set(_LAYERS) or any(type(value) is not bool for value in layers.values()):
            raise ValueError("layers must be a nonempty map of supported boolean layer values")
        controls.append(("layers", layers))
    if not controls:
        raise ValueError("sentinel.view.set requires symbol, timeframe, viewport or layers")
    return controls


async def set_sentinel_view(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    try:
        args = request.arguments
        controls = _controls(args)
        wait_ms = _int_argument(args, "waitMs", 5000, 5000)
        screenshot = args.get("screenshot", False)
        if type(screenshot) is not bool:
            raise ValueError("screenshot must be boolean")
        screenshot_name = args.get("screenshotName", "agent-view")
        screenshot_target = args.get("screenshotTarget", "main")
        if not isinstance(screenshot_name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", screenshot_name) or screenshot_target not in {"main", "heatmap", "lab"}:
            raise ValueError("screenshotName or screenshotTarget is invalid")
        if approval_key(request) not in context.ephemeral.get("barricade_approved", set()):
            return ToolExecutionResult(tool_id=request.tool_id, ok=False, summary="Sentinel view change requires operator approval.",
                                       error="approval required", output={"target": ", ".join(kind for kind, _ in controls),
                                       "policyDecision": "approval_required", "policySummary": "This call changes the owner's visible Sentinel GUI view."})
        operations: list[dict] = []
        for kind, payload in controls:
            applied = await sentinel_request("POST", f"/api/v1/{kind}", payload=payload, timeout=3.0)
            operation_id = applied["data"].get("operationId")
            if not isinstance(operation_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", operation_id):
                raise SentinelApiError("invalid_response", "Sentinel control response has no valid operationId.")
            waited = await sentinel_request("GET", f"/api/v1/operations/{operation_id}",
                                            params={"waitMs": wait_ms}, timeout=wait_ms / 1000 + 1.0)
            operations.append({"kind": kind, "applied": applied, "operation": waited})
            status = waited["data"].get("status")
            if status != "rendered":
                code = "render_timeout" if status == "applied" else "operation_not_rendered"
                return ToolExecutionResult(tool_id=request.tool_id, ok=False,
                                           summary=f"Sentinel {kind} operation {operation_id} is {status}.", error=code,
                                           output={"operations": operations, "meta": waited["meta"], "code": code})
            if not waited["data"].get("frameId"):
                raise SentinelApiError("invalid_response", "Sentinel reported a rendered operation without frameId.")
        output: dict[str, Any] = {"operations": operations, "meta": operations[-1]["operation"]["meta"],
                                  "frame": operations[-1]["operation"]["data"]}
        if screenshot:
            operation_id = operations[-1]["operation"]["data"]["operationId"]
            output["screenshot"] = await sentinel_request("GET", "/api/v1/screenshot",
                params={"name": screenshot_name, "target": screenshot_target,
                        "afterOperation": operation_id, "waitMs": wait_ms}, timeout=wait_ms / 1000 + 1.0,
                screenshot=True)
        return ToolExecutionResult(tool_id=request.tool_id, ok=True,
                                   summary=f"Sentinel view rendered in frame {output['frame'].get('frameId')}",
                                   output=output, model_body=_control_model_body(output))
    except (SentinelApiError, ValueError) as exc:
        return _error(request, exc)


HANDLERS = {descriptor.id: (set_sentinel_view if descriptor.id == "sentinel.view.set" else read_sentinel)
            for descriptor in DESCRIPTORS}
