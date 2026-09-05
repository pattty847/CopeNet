"""Versioned boundary contracts and immutable authority for chart turns."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CHART_TOOL_IDS = (
    "market.chart.context", "market.chart.read", "market.chart.document",
    "market.chart.apply", "market.chart.undo",
)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class InstrumentRef(Contract):
    instrumentId: str = Field(min_length=1, max_length=180)
    symbol: str = Field(min_length=1, max_length=32)
    assetClass: str = Field(min_length=1, max_length=32)
    source: str = Field(min_length=1, max_length=80)
    currency: str | None = Field(default=None, min_length=1, max_length=16)


class Viewport(Contract):
    from_: int | None = Field(default=None, alias="from")
    to: int | None = None
    logicalFrom: float | None = None
    logicalTo: float | None = None


class Selection(Contract):
    from_: int = Field(alias="from")
    to: int

    @model_validator(mode="after")
    def ordered(self):
        if self.from_ > self.to:
            raise ValueError("Selection start must not exceed end")
        return self


class Resource(Contract):
    key: str = Field(min_length=1, max_length=120)
    kind: Literal["candles", "indicator", "financial", "comparison", "evidence", "panel", "quote", "drawings"]
    label: str = Field(min_length=1, max_length=160)
    unit: str | None = Field(default=None, max_length=80)
    status: Literal["loaded", "empty", "stale", "error", "not-loaded"]
    observedAt: str | None = Field(default=None, max_length=80)
    rows: list[dict[str, Any]] = Field(max_length=25000)
    metadata: dict[str, Any]


class Capture(Contract):
    schemaVersion: Literal[1]
    viewId: str = Field(min_length=1, max_length=160)
    viewRevision: int = Field(ge=0)
    instrument: InstrumentRef
    timeframe: Literal["D", "W", "M"]
    range: str = Field(max_length=32)
    viewport: Viewport
    selection: Selection | None
    settings: dict[str, Any]
    resources: list[Resource] = Field(max_length=32)
    documentId: str = Field(min_length=1, max_length=160)
    documentRevision: int = Field(ge=0)

    @field_validator("schemaVersion", mode="before")
    @classmethod
    def version_number(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("Unsupported chart capture schemaVersion")
        return value

    @model_validator(mode="after")
    def unique_resources(self):
        keys = [resource.key for resource in self.resources]
        if len(keys) != len(set(keys)):
            raise ValueError("Resource keys must be unique")
        return self


class Anchor(Contract):
    t: int = Field(ge=0, le=9007199254740991)
    value: float


class EvidenceRef(Contract):
    observationId: str = Field(min_length=1, max_length=160)
    resourceKey: str = Field(min_length=1, max_length=120)
    from_: int | None = Field(default=None, alias="from")
    to: int | None = None


class Owner(Contract):
    kind: Literal["agent", "operator"]
    sessionKey: str | None = None
    runId: str | None = None


class ChartObject(Contract):
    id: str = Field(min_length=1, max_length=160)
    kind: Literal["level", "zone", "trendline", "label"]
    anchors: list[Anchor] = Field(min_length=1, max_length=2)
    timeframe: Literal["D", "W", "M"]
    label: str = Field(max_length=240)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    visible: bool = True
    rationale: str = Field(default="", max_length=4000)
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=20)
    owner: Owner = Field(default_factory=lambda: Owner(kind="operator"))

    @model_validator(mode="after")
    def anchor_count(self):
        expected = 2 if self.kind in ("zone", "trendline") else 1
        if len(self.anchors) != expected:
            raise ValueError(f"{self.kind} requires {expected} anchors")
        return self


class Operation(Contract):
    kind: Literal["create", "update", "delete"]
    object: ChartObject | None = None
    objectId: str | None = None
    patch: dict[str, Any] | None = None

    @model_validator(mode="after")
    def shape(self):
        if self.kind == "create" and (self.object is None or self.objectId or self.patch):
            raise ValueError("Create requires only object")
        if self.kind != "create" and (not self.objectId or self.object is not None):
            raise ValueError("Update/delete requires objectId")
        if self.kind == "update" and not self.patch:
            raise ValueError("Update requires patch")
        if self.kind == "delete" and self.patch is not None:
            raise ValueError("Delete does not accept patch")
        if self.patch and (set(self.patch) - {"anchors", "label", "color", "visible", "rationale", "evidence"}):
            raise ValueError("Patch may change anchors, label, color, visible, rationale, evidence")
        return self


class ApplyRequest(Contract):
    documentId: str = Field(min_length=1, max_length=160)
    expectedRevision: int = Field(ge=0)
    operationId: str = Field(min_length=1, max_length=160)
    operations: list[Operation] = Field(min_length=1, max_length=20)


class UndoRequest(Contract):
    documentId: str = Field(min_length=1, max_length=160)
    expectedRevision: int = Field(ge=0)
    operationId: str = Field(min_length=1, max_length=160)
    batchId: str = Field(min_length=1, max_length=160)


@dataclass(frozen=True)
class MarketTurnContext:
    observation_id: str
    document_id: str
    view_id: str
    session_key: str
    run_id: str
    detail: str = "balanced"
    access: str = "read"
    include_account_context: bool = False
    resource_keys: tuple[str, ...] = ()
    allowed_tool_ids: tuple[str, ...] = CHART_TOOL_IDS
    forecast_id: str | None = None
    forecast_lane: str | None = None
