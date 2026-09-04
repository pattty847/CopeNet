"""Transport and model-tool request boundaries."""
from typing import Any, Literal
from pydantic import Field, model_validator
from .models import Contract


class WorkspaceRequest(Contract):
    workspaceId: str = Field(default="primary", min_length=1, max_length=160)
    instrument: dict[str, Any]


class WorkspaceUpdate(Contract):
    workspaceId: str = Field(default="primary", min_length=1, max_length=160)
    sessionKey: str | None


class CaptureRequest(Contract):
    sessionKey: str = Field(min_length=1, max_length=160)
    captureId: str = Field(min_length=1, max_length=160)
    capture: dict[str, Any]


class DocumentRequest(Contract):
    documentId: str = Field(min_length=1, max_length=160)


class RenderRequest(Contract):
    documentId: str = Field(min_length=1, max_length=160)
    revision: int = Field(ge=0)
    viewId: str = Field(min_length=1, max_length=160)
    status: Literal["rendered", "hidden", "failed"]
    objectIds: list[str] = Field(default_factory=list, max_length=200)
    reason: str | None = Field(default=None, max_length=1000)


class ReadRequest(Contract):
    resourceKey: str = Field(min_length=1, max_length=120)
    observationId: str | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=2000)
    from_: int | None = Field(default=None, alias="from")
    to: int | None = None
    fields: list[str] | None = Field(default=None, max_length=30)
    metadataPath: list[str | int] | None = Field(default=None, max_length=12)


class DocumentToolRequest(Contract):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=200)


class ObservationReadRequest(ReadRequest):
    sessionKey: str | None = Field(default=None, min_length=1, max_length=160)
    documentId: str | None = Field(default=None, min_length=1, max_length=160)
    observationId: str = Field(min_length=1, max_length=160)
    detail: Literal["quick", "balanced", "deep"] = "balanced"
    includeAccountContext: bool = False

    @model_validator(mode="after")
    def evidence_identity(self):
        if not self.sessionKey and not self.documentId:
            raise ValueError("Supply a sessionKey or a drawing document reference")
        return self
