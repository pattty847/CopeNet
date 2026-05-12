"""Workspace intelligence tool handlers."""

from __future__ import annotations

from pathlib import Path

from copenet.core.tools.contracts import ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult
from ._shared import resolve_relative_path


DESCRIPTORS = [
    ToolDescriptor(
        id='repo.map',
        name='Repository Map',
        description='Build a cached workspace map with stack, manifests, entrypoints, CI hints, subsystems, and recommended verification checks.',
        category='repo-read',
        input_schema={
            'type': 'object',
            'properties': {
                'workspaceRoot': {'type': 'string'},
                'path': {'type': 'string'},
                'refresh': {'type': 'boolean'},
            },
        },
        capabilities=['workspace', 'repo_map', 'verification'],
    ),
    ToolDescriptor(
        id='test.discover',
        name='Discover Tests',
        description='Detect the cheapest meaningful test, lint, build, and typecheck commands for the current workspace.',
        category='repo-read',
        input_schema={
            'type': 'object',
            'properties': {
                'workspaceRoot': {'type': 'string'},
                'refresh': {'type': 'boolean'},
            },
        },
        capabilities=['workspace', 'verification', 'tests'],
    ),
]


async def repo_map(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    service = context.workspace_intel_service
    if service is None:
        raise RuntimeError('workspace intelligence service unavailable')
    workspace_root = _workspace_root_from_request(request, context)
    payload = service.get_workspace_map(workspace_root, refresh=bool(request.arguments.get('refresh')))
    summary = f"Mapped workspace {payload['workspaceRoot']} with {len(payload['languages'])} language signals and {len(payload['verificationHints'])} verification hints."
    return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary=summary, output=payload)


async def test_discover(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    service = context.workspace_intel_service
    if service is None:
        raise RuntimeError('workspace intelligence service unavailable')
    workspace_root = _workspace_root_from_request(request, context)
    payload = service.discover_tests(workspace_root, refresh=bool(request.arguments.get('refresh')))
    summary = f"Discovered {len(payload['commands'])} verification commands for {payload['workspaceRoot']}."
    return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary=summary, output=payload)


HANDLERS = {
    'repo.map': repo_map,
    'test.discover': test_discover,
}


def _workspace_root_from_request(request: ToolExecutionRequest, context: ToolExecutionContext) -> Path:
    requested = str(request.arguments.get('workspaceRoot') or request.arguments.get('path') or '').strip()
    return resolve_relative_path(requested, context) if requested else context.session_workspace_root
