"""Strict forecast submission contracts; attribution comes from the admitted run."""
from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, model_validator

from ..chart_workspace.models import Contract, EvidenceRef, InstrumentRef

FORECAST_TOOL_IDS = ('market.forecast.submit', 'market.forecast.read')

Identifier = Annotated[str, Field(min_length=1, max_length=160)]
Price = Annotated[float, Field(gt=0)]


class ForecastRequest(Contract):
    requestId: Identifier
    documentId: Identifier
    observationId: Identifier
    sessionKey: Identifier
    instrument: InstrumentRef
    provider: Identifier
    model: Identifier
    detail: Literal['quick', 'balanced', 'deep'] = 'balanced'
    paired: bool = False
    entryExpirySessions: int = Field(default=10, ge=1, le=40)
    trackingScanId: Identifier | None = None


class Entry(Contract):
    kind: Literal['limit', 'stop']
    price: Price


class Target(Contract):
    price: Price
    fraction: float = Field(gt=0, le=1)


class Zone(Contract):
    label: str = Field(min_length=1, max_length=160)
    lower: Price
    upper: Price

    @model_validator(mode='after')
    def ordered(self):
        if self.lower >= self.upper:
            raise ValueError('Zone lower must be below upper')
        return self


class Setup(Contract):
    kind: Literal['setup']
    direction: Literal['long', 'short']
    thesis: str = Field(min_length=1, max_length=8000)
    entry: Entry
    stop: Price
    targets: list[Target] = Field(min_length=1, max_length=3)
    zones: list[Zone] = Field(default_factory=list, max_length=4)
    evidence: list[EvidenceRef] = Field(min_length=1, max_length=20)

    @model_validator(mode='after')
    def executable_order(self):
        sign = 1 if self.direction == 'long' else -1
        if sign * (self.entry.price - self.stop) <= 0:
            raise ValueError('Protective stop must be on the risk side of entry')
        previous = self.entry.price
        for target in self.targets:
            if sign * (target.price - previous) <= 0:
                raise ValueError('Targets must be distinct and ordered away from entry')
            previous = target.price
        if not math.isclose(sum(target.fraction for target in self.targets), 1, abs_tol=1e-9):
            raise ValueError('Target exit fractions must total 1')
        for ref in self.evidence:
            if ref.from_ is not None and ref.to is not None and ref.from_ > ref.to:
                raise ValueError('Evidence range must be ordered')
        return self


class NoSetup(Contract):
    kind: Literal['no_setup']
    thesis: str = Field(min_length=1, max_length=8000)


class Directional(Contract):
    kind: Literal['directional']
    direction: Literal['bullish', 'bearish', 'neutral', 'abstain']
    thesis: str = Field(min_length=1, max_length=8000)


Submission = Annotated[Setup | NoSetup | Directional, Field(discriminator='kind')]
SUBMISSION_ADAPTER = TypeAdapter(Submission)


def validate_submission(raw: dict, lane: str) -> dict:
    result = SUBMISSION_ADAPTER.validate_python(raw).model_dump(by_alias=True)
    if lane not in ('ta', 'directional') or (result['kind'] == 'directional') != (lane == 'directional'):
        raise ValueError('Submission kind does not match admitted forecast lane')
    return result
