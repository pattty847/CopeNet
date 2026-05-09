"""Built-in CopeNet tool handlers."""

from __future__ import annotations

from .contracts import ToolBlockedError, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult
from .handlers.artifacts import DESCRIPTORS as ARTIFACT_DESCRIPTORS, HANDLERS as ARTIFACT_HANDLERS
from .handlers.context import DESCRIPTORS as CONTEXT_DESCRIPTORS, HANDLERS as CONTEXT_HANDLERS
from .handlers.files import DESCRIPTORS as FILE_DESCRIPTORS, HANDLERS as FILE_HANDLERS
from .handlers.git import DESCRIPTORS as GIT_DESCRIPTORS, HANDLERS as GIT_HANDLERS
from .handlers.shell import DESCRIPTORS as SHELL_DESCRIPTORS, HANDLERS as SHELL_HANDLERS


ALL_DESCRIPTORS = CONTEXT_DESCRIPTORS + FILE_DESCRIPTORS + GIT_DESCRIPTORS + SHELL_DESCRIPTORS + ARTIFACT_DESCRIPTORS
ALL_HANDLERS = {
    **CONTEXT_HANDLERS,
    **FILE_HANDLERS,
    **GIT_HANDLERS,
    **SHELL_HANDLERS,
    **ARTIFACT_HANDLERS,
}


class BuiltinReadonlyTools:
    """Built-in tool implementations used by the default registry."""

    def descriptors(self):
        return ALL_DESCRIPTORS

    async def run(self, request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
        handler = ALL_HANDLERS.get(request.tool_id)
        if handler is None:
            raise ToolBlockedError(f"unknown builtin tool: {request.tool_id}")
        return await handler(request, context)
