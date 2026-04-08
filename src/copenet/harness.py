"""Compatibility shim — implementation moved to copenet.core.harness."""
from copenet.core.harness import (  # noqa: F401
    ChatHarness,
    HarnessResult,
    HarnessTurnPlan,
    ModelCapabilityProfile,
    ToolExecutor,
    TraceRecorder,
)

__all__ = ["ChatHarness", "HarnessResult", "HarnessTurnPlan", "ModelCapabilityProfile", "ToolExecutor", "TraceRecorder"]
