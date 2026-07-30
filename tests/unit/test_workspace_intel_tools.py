from __future__ import annotations

import json
from pathlib import Path

import pytest

from copenet.core.runtime import ArtifactStore
from copenet.core.tools import ToolExecutionContext, ToolExecutionRequest, ToolPolicy, ToolRegistry
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.core.workspace_intel.models import WorkspaceIntelRecord
from copenet.core.workspace_intel import WorkspaceIntelService, WorkspaceIntelStore


def _tool_context(tmp_path: Path, *, policy: ToolPolicy | None = None, task_prompt_id: str | None = None) -> ToolExecutionContext:
    registry = ToolRegistry()
    return ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key='alpha',
        provider_name='prompted',
        model='test-model',
        session_store=SessionStore(path=tmp_path / 'index.json'),
        transcript_store=TranscriptStore(root_dir=tmp_path / 'history'),
        providers={},
        policy=policy or ToolPolicy(),
        available_tools=registry.list_tools(),
        workspace_intel_service=WorkspaceIntelService(WorkspaceIntelStore(path=tmp_path / 'workspace-intel.json')),
        artifact_store=ArtifactStore(root_dir=tmp_path / 'artifacts'),
        task_prompt_id=task_prompt_id,
        run_id='run-test',
    )


def _seed_repo(tmp_path: Path) -> None:
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src' / 'main.py').write_text('print("hello")\n', encoding='utf-8')
    (tmp_path / 'src' / 'main.ts').write_text('console.log("hello")\n', encoding='utf-8')
    (tmp_path / 'pyproject.toml').write_text('[tool.pytest.ini_options]\naddopts = "-q"\n', encoding='utf-8')
    for path in [
        tmp_path / 'src' / 'copenet' / 'core' / 'orchestrator',
        tmp_path / 'src' / 'copenet' / 'core' / 'harness',
        tmp_path / 'src' / 'copenet' / 'core' / 'tools',
        tmp_path / 'src' / 'copenet' / 'host' / 'frontend',
    ]:
        path.mkdir(parents=True, exist_ok=True)
        (path / '__init__.py').write_text('', encoding='utf-8')
    frontend = tmp_path / 'src' / 'frontend'
    frontend.mkdir(parents=True)
    (frontend / 'package.json').write_text(json.dumps({
        'name': 'intel-frontend',
        'scripts': {
            'test': 'vitest run',
            'lint': 'eslint .',
            'build': 'vite build',
            'typecheck': 'tsc --noEmit'
        }
    }), encoding='utf-8')
    (frontend / 'package-lock.json').write_text('{}', encoding='utf-8')
    (tmp_path / '.github').mkdir()
    (tmp_path / '.github' / 'workflows').mkdir()
    (tmp_path / '.github' / 'workflows' / 'ci.yml').write_text('name: ci\n', encoding='utf-8')
    claude_frontend = tmp_path / '.claude' / 'worktrees' / 'demo' / 'src' / 'frontend'
    claude_frontend.mkdir(parents=True)
    (claude_frontend / 'package.json').write_text(json.dumps({'scripts': {'build': 'vite build'}}), encoding='utf-8')
    (tmp_path / '.pytest_cache').mkdir()
    (tmp_path / '.pytest_cache' / 'README.md').write_text('cache docs\n', encoding='utf-8')


@pytest.mark.asyncio
async def test_repo_map_detects_workspace_stack_and_verification_hints(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    registry = ToolRegistry()

    result = await registry.execute(
        ToolExecutionRequest(tool_id='repo.map', arguments={'path': '.'}),
        _tool_context(tmp_path),
    )

    assert result.ok is True
    assert result.output['workspaceRoot'] == str(tmp_path)
    assert 'python' in result.output['languages']
    assert 'typescript' in result.output['languages']
    assert 'npm' in result.output['packageManagers']
    assert any(item['path'] == 'src/frontend/package.json' for item in result.output['configFiles'])
    assert not any('.claude' in item['path'] for item in result.output['configFiles'])
    assert any(item['path'] == '.github/workflows/ci.yml' for item in result.output['ciWorkflows'])
    assert any(command['kind'] == 'test' for command in result.output['verificationHints'])
    assert not any('.claude' in command['command'] for command in result.output['verificationHints'])
    subsystem_roots = {item['root'] for item in result.output['subsystems']}
    assert {'src/copenet/core/orchestrator', 'src/copenet/core/harness', 'src/copenet/core/tools', 'src/copenet/host/frontend'}.issubset(subsystem_roots)
    assert '.pytest_cache' not in subsystem_roots


@pytest.mark.asyncio
async def test_test_discover_returns_ranked_commands_and_cache_status(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    registry = ToolRegistry()
    context = _tool_context(tmp_path)

    first = await registry.execute(
        ToolExecutionRequest(tool_id='test.discover', arguments={}),
        context,
    )
    second = await registry.execute(
        ToolExecutionRequest(tool_id='test.discover', arguments={}),
        context,
    )

    assert first.ok is True
    assert first.output['cacheStatus'] in {'fresh', 'refreshed'}
    assert second.output['cacheStatus'] == 'cached'
    assert second.output['recommendedDefaultChecks']
    assert not any('--extra dev' in command['command'] for command in second.output['commands'])
    assert any(command['kind'] == 'lint' and command['command'] == 'cd src/frontend && npm run lint' for command in second.output['commands'])
    assert any(command['kind'] == 'typecheck' and command['command'] == 'cd src/frontend && npm run typecheck' for command in second.output['commands'])


def test_workspace_intel_refreshes_legacy_cache_records(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    store = WorkspaceIntelStore(path=tmp_path / 'workspace-intel.json')
    root = tmp_path.resolve()
    store.save(
        WorkspaceIntelRecord(
            workspace_root=str(root),
            fingerprint='legacy-fingerprint',
            schema_version=1,
            package_managers=['uv'],
            recommended_default_checks=['uv run --extra dev pytest -q'],
            generated_at='2026-05-11T00:00:00+00:00',
        )
    )

    service = WorkspaceIntelService(store)
    result = service.get_workspace_map(root)

    assert result['cacheStatus'] == 'refreshed'
    assert any(item['path'] == 'src/frontend/package.json' for item in result['configFiles'])
    assert 'npm' in result['packageManagers']


def test_workspace_intel_honors_copenetignore_for_named_file_scans(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    scratch_frontend = tmp_path / 'scratch' / 'frontend'
    scratch_frontend.mkdir(parents=True)
    (scratch_frontend / 'package.json').write_text(json.dumps({'scripts': {'build': 'vite build'}}), encoding='utf-8')
    (tmp_path / '.copenetignore').write_text('scratch/**\n', encoding='utf-8')

    service = WorkspaceIntelService(WorkspaceIntelStore(path=tmp_path / 'workspace-intel.json'))
    result = service.get_workspace_map(tmp_path)

    assert not any(item['path'].startswith('scratch/') for item in result['configFiles'])
    assert not any('scratch/' in command['command'] for command in result['verificationHints'])


def test_workspace_intel_uses_uv_dev_extra_only_when_declared(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    (tmp_path / 'pyproject.toml').write_text(
        '[project.optional-dependencies]\n'
        'dev = ["pytest>=8"]\n'
        '\n'
        '[tool.pytest.ini_options]\n'
        'addopts = "-q"\n',
        encoding='utf-8',
    )

    service = WorkspaceIntelService(WorkspaceIntelStore(path=tmp_path / 'workspace-intel.json'))
    result = service.discover_tests(tmp_path)

    assert any(command['command'] == 'uv run --extra dev pytest -q' for command in result['commands'])


@pytest.mark.asyncio
async def test_files_read_returns_digest_and_bounded_window(tmp_path: Path) -> None:
    sample = tmp_path / 'README.md'
    sample.write_text('0123456789abcdefghijklmnopqrstuvwxyz', encoding='utf-8')
    registry = ToolRegistry()

    result = await registry.execute(
        ToolExecutionRequest(tool_id='files.read', arguments={'path': 'README.md', 'offset': 10, 'limit': 8}),
        _tool_context(tmp_path),
    )

    assert result.ok is True
    # Phase 0.2: when truncated, files.read appends an English continuation
    # hint to the returned `content` so the model knows how to paginate.
    assert result.output['content'].startswith('abcdefgh')
    assert '[Read truncated at char 18' in result.output['content']
    assert 'Use offset=18 to continue' in result.output['content']
    assert result.output['offset'] == 10
    assert result.output['limit'] == 8
    assert result.output['truncated'] is True
    assert result.output['nextOffset'] == 18
    assert result.output['digest']


@pytest.mark.asyncio
async def test_files_edit_rejects_stale_expected_digest(tmp_path: Path) -> None:
    sample = tmp_path / 'README.md'
    sample.write_text('hello world\n', encoding='utf-8')
    registry = ToolRegistry()
    context = _tool_context(
        tmp_path,
        policy=ToolPolicy(allowed_categories={'repo-read', 'repo-write', 'shell-read', 'context', 'artifact'}),
        task_prompt_id='full-access',
    )

    read_result = await registry.execute(
        ToolExecutionRequest(tool_id='files.read', arguments={'path': 'README.md'}),
        context,
    )
    sample.write_text('hello changed world\n', encoding='utf-8')

    edit_result = await registry.execute(
        ToolExecutionRequest(
            tool_id='files.edit',
            arguments={
                'path': 'README.md',
                'old_text': 'changed',
                'new_text': 'updated',
                'expected_digest': read_result.output['digest'],
            },
        ),
        context,
    )

    assert edit_result.ok is False
    assert 'stale read detected' in str(edit_result.error)
