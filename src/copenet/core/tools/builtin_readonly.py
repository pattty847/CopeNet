"""Built-in CopeNet tool handlers."""

from __future__ import annotations

from .contracts import ToolBlockedError, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult
from .handlers.artifacts import DESCRIPTORS as ARTIFACT_DESCRIPTORS, HANDLERS as ARTIFACT_HANDLERS
from .handlers.files import DESCRIPTORS as FILE_DESCRIPTORS, HANDLERS as FILE_HANDLERS
from .handlers.git import DESCRIPTORS as GIT_DESCRIPTORS, HANDLERS as GIT_HANDLERS
from .handlers.memory import DESCRIPTORS as MEMORY_DESCRIPTORS, HANDLERS as MEMORY_HANDLERS
from .handlers.persona import DESCRIPTORS as PERSONA_DESCRIPTORS, HANDLERS as PERSONA_HANDLERS
from .handlers.plan import DESCRIPTORS as PLAN_DESCRIPTORS, HANDLERS as PLAN_HANDLERS
from .handlers.shell import DESCRIPTORS as SHELL_DESCRIPTORS, HANDLERS as SHELL_HANDLERS
from .handlers.user_note import DESCRIPTORS as USER_NOTE_DESCRIPTORS, HANDLERS as USER_NOTE_HANDLERS
from .handlers.web import DESCRIPTORS as WEB_DESCRIPTORS, HANDLERS as WEB_HANDLERS
from .handlers.workspace_intel import DESCRIPTORS as WORKSPACE_INTEL_DESCRIPTORS, HANDLERS as WORKSPACE_INTEL_HANDLERS


# Phase 3 (HARNESS_REBUILD_V2): trim the MODEL-FACING tool manifest to the five
# primitives. The model now sees exactly: files.read, files.write, files.edit,
# files.rg, shell.exec. context.prepare was retired in Phase 0.3.
#
# git.* (use shell.exec git), repo.map / test.discover (explore via primitives),
# files.list (shell.exec ls) and files.search (duplicate of files.rg) are dropped
# from the manifest. memory.* and artifact.create are DEFERRED per §3.6 — they
# come back when redesigned with explicit opt-in.
#
# Handlers for the dropped tools are intentionally still registered so internal
# callers and the probe/characterization test suite keep working; the dead
# handler files themselves are deleted in the Phase 5 sweep, where subtraction
# is explicitly safe. ALL_HANDLERS therefore stays a superset of MANIFEST_TOOL_IDS.
MANIFEST_TOOL_IDS = {
    "files.read",
    "files.write",
    "files.edit",
    "files.rg",
    "shell.exec",
    "plan.write",
    "web.search",
    "web.fetch",
    "persona.author",
    # Memory came back into the manifest redesigned as draft-first (§3.6 opt-in):
    # memory.read recalls, memory.write PROPOSES a draft that the operator approves.
    "memory.read",
    "memory.write",
    # user.remember PROPOSES a USER.md identity delta the operator approves (draft-first).
    "user.remember",
}

# ALL_DESCRIPTORS stays the full set so the registry can still ROUTE + policy-check
# every handler (internal callers, the probe suite, and direct tests). The
# model-facing manifest is filtered to MANIFEST_TOOL_IDS by ToolRegistry.list_tools().
ALL_DESCRIPTORS = (
    FILE_DESCRIPTORS
    + GIT_DESCRIPTORS
    + SHELL_DESCRIPTORS
    + ARTIFACT_DESCRIPTORS
    + MEMORY_DESCRIPTORS
    + PERSONA_DESCRIPTORS
    + WORKSPACE_INTEL_DESCRIPTORS
    + PLAN_DESCRIPTORS
    + WEB_DESCRIPTORS
    + USER_NOTE_DESCRIPTORS
)
ALL_HANDLERS = {
    **FILE_HANDLERS,
    **GIT_HANDLERS,
    **MEMORY_HANDLERS,
    **PERSONA_HANDLERS,
    **SHELL_HANDLERS,
    **ARTIFACT_HANDLERS,
    **WORKSPACE_INTEL_HANDLERS,
    **PLAN_HANDLERS,
    **WEB_HANDLERS,
    **USER_NOTE_HANDLERS,
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
