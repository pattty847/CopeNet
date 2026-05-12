"""Workspace intelligence detection and cache orchestration."""

from __future__ import annotations

import hashlib
import fnmatch
import json
from pathlib import Path
import re
import subprocess
from typing import Iterable
from datetime import datetime, timezone

from .models import WorkspaceEntryPoint, WorkspaceFileHint, WorkspaceIntelRecord, WorkspaceSubsystem, VerificationCommand, WorkspaceCacheStatus
from .store import WorkspaceIntelStore

WORKSPACE_INTEL_SCHEMA_VERSION = 2
DEFAULT_IGNORED_PARTS = {
    '.git',
    '.claude',
    '.copenet',
    '.agents',
    '.cursor',
    '.pytest_cache',
    '.next',
    '.cache',
    '.venv',
    '__pycache__',
    'node_modules',
    'dist',
    'build',
    'coverage',
    'target',
    'worktrees',
}
SIGNAL_FILE_NAMES = (
    'package.json',
    'package-lock.json',
    'pnpm-lock.yaml',
    'yarn.lock',
    'tsconfig.json',
    'vite.config.ts',
    'vitest.config.ts',
)


class WorkspaceIntelService:
    """Build and cache bounded workspace intelligence summaries."""

    def __init__(self, store: WorkspaceIntelStore) -> None:
        self._store = store

    def get_workspace_map(self, workspace_root: str | Path, *, refresh: bool = False) -> dict[str, object]:
        record, cache_status = self._resolve_record(workspace_root, refresh=refresh)
        return record.to_public_dict(cache_status=cache_status)

    def discover_tests(self, workspace_root: str | Path, *, refresh: bool = False) -> dict[str, object]:
        record, cache_status = self._resolve_record(workspace_root, refresh=refresh)
        return record.to_test_discovery_dict(cache_status=cache_status)

    def get_summary(self, workspace_root: str | Path, *, refresh: bool = False) -> dict[str, object]:
        record, cache_status = self._resolve_record(workspace_root, refresh=refresh)
        return {
            'workspaceRoot': record.workspace_root,
            'cacheStatus': cache_status,
            'languages': list(record.languages),
            'packageManagers': list(record.package_managers),
            'recommendedDefaultChecks': list(record.recommended_default_checks),
        }

    def _resolve_record(self, workspace_root: str | Path, *, refresh: bool) -> tuple[WorkspaceIntelRecord, WorkspaceCacheStatus]:
        root = Path(workspace_root).expanduser().resolve()
        scan = WorkspaceScan(root)
        fingerprint = _workspace_fingerprint(root, scan)
        cached = self._store.get(str(root))
        if cached is not None and cached.schema_version == WORKSPACE_INTEL_SCHEMA_VERSION and cached.fingerprint == fingerprint and not refresh:
            return cached, 'cached'
        record = _build_record(root, fingerprint, scan)
        self._store.save(record)
        return record, ('refreshed' if refresh or cached is not None else 'fresh')


class WorkspaceScan:
    """One bounded workspace scan with ignore rules and named-file caching."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.ignore_patterns = _load_copenetignore(root)
        self._named_files: dict[str, list[Path]] = {}

    def is_ignored(self, path: Path) -> bool:
        try:
            rel = path.relative_to(self.root)
        except ValueError:
            return False
        rel_text = rel.as_posix()
        parts = set(rel.parts)
        if parts & DEFAULT_IGNORED_PARTS:
            return True
        for pattern in self.ignore_patterns:
            normalized = pattern.rstrip('/')
            if not normalized:
                continue
            if fnmatch.fnmatch(rel_text, normalized) or fnmatch.fnmatch(rel_text, f'{normalized}/**'):
                return True
            if rel_text == normalized or rel_text.startswith(f'{normalized}/'):
                return True
        return False

    def named_files(self, name: str) -> list[Path]:
        if name not in self._named_files:
            self._named_files[name] = [
                path for path in self.root.rglob(name)
                if path.is_file() and not self.is_ignored(path)
            ]
        return list(self._named_files[name])


def _load_copenetignore(root: Path) -> list[str]:
    path = root / '.copenetignore'
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except OSError:
        return []
    patterns: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            patterns.append(stripped)
    return patterns


def _workspace_fingerprint(root: Path, scan: WorkspaceScan) -> str:
    head = _git_head(root)
    signal_paths = [
        root / 'pyproject.toml',
        root / 'requirements.txt',
        root / 'uv.lock',
        root / '.copenetignore',
        *[path for name in SIGNAL_FILE_NAMES for path in scan.named_files(name)],
    ]
    parts = [str(root), head, f'schema:{WORKSPACE_INTEL_SCHEMA_VERSION}']
    for path in sorted({item for item in signal_paths if item.exists()}):
        if path.exists():
            stat = path.stat()
            rel = path.relative_to(root) if path.is_absolute() and root in path.parents else Path(path.name)
            parts.append(f'{rel}:{int(stat.st_mtime_ns)}:{stat.st_size}')
    return hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()


def _git_head(root: Path) -> str:
    try:
        completed = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=str(root), capture_output=True, text=True, timeout=2, check=False)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return ''
    return (completed.stdout or '').strip() if completed.returncode == 0 else ''


def _build_record(root: Path, fingerprint: str, scan: WorkspaceScan) -> WorkspaceIntelRecord:
    top_level_paths = sorted(path.name for path in root.iterdir() if not scan.is_ignored(path))[:32]
    config_files = _detect_config_files(root, scan)
    package_managers = _detect_package_managers(root, scan)
    scripts = _load_package_scripts(root, scan)
    languages = _detect_languages(root, scan)
    ci_workflows = _detect_ci_workflows(root)
    entrypoints = _detect_entrypoints(root, scripts)
    subsystems = _detect_subsystems(root, scan)
    verification_hints = _detect_verification_commands(root, scan, scripts)
    recommended = [command.command for command in verification_hints[:3]]
    return WorkspaceIntelRecord(
        workspace_root=str(root),
        fingerprint=fingerprint,
        schema_version=WORKSPACE_INTEL_SCHEMA_VERSION,
        top_level_paths=top_level_paths,
        languages=languages,
        package_managers=package_managers,
        config_files=config_files,
        scripts=scripts,
        ci_workflows=ci_workflows,
        entrypoints=entrypoints,
        subsystems=subsystems,
        verification_hints=verification_hints,
        recommended_default_checks=recommended,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def _detect_config_files(root: Path, scan: WorkspaceScan) -> list[WorkspaceFileHint]:
    hints: list[WorkspaceFileHint] = []
    candidates = [
        ('package.json', 'node_manifest'),
        ('pyproject.toml', 'python_manifest'),
        ('requirements.txt', 'python_requirements'),
        ('uv.lock', 'python_lockfile'),
        ('tsconfig.json', 'typescript_config'),
        ('vite.config.ts', 'vite_config'),
        ('vitest.config.ts', 'vitest_config'),
        ('pytest.ini', 'pytest_config'),
    ]
    for name, kind in candidates:
        if (root / name).is_file():
            hints.append(WorkspaceFileHint(path=name, kind=kind))
    for manifest in _package_manifests(root, scan):
        rel = str(manifest.relative_to(root))
        if rel != 'package.json':
            hints.append(WorkspaceFileHint(path=rel, kind='node_manifest'))
    return hints[:16]


def _detect_package_managers(root: Path, scan: WorkspaceScan) -> list[str]:
    managers: list[str] = []
    if _package_manifests(root, scan):
        if list(_iter_named_files(root, 'pnpm-lock.yaml', scan)):
            managers.append('pnpm')
        elif list(_iter_named_files(root, 'yarn.lock', scan)):
            managers.append('yarn')
        else:
            managers.append('npm')
    if (root / 'pyproject.toml').is_file() or (root / 'uv.lock').is_file():
        managers.append('uv')
    elif (root / 'requirements.txt').is_file():
        managers.append('pip')
    return managers


def _detect_languages(root: Path, scan: WorkspaceScan) -> list[str]:
    mapping = {
        'python': ['.py'],
        'typescript': ['.ts', '.tsx'],
        'javascript': ['.js', '.jsx'],
        'markdown': ['.md'],
    }
    seen: set[str] = set()
    for path in _iter_code_files(root, scan):
        suffix = path.suffix.lower()
        for language, suffixes in mapping.items():
            if suffix in suffixes:
                seen.add(language)
    return sorted(seen)


def _iter_code_files(root: Path, scan: WorkspaceScan) -> Iterable[Path]:
    for path in root.rglob('*'):
        if scan.is_ignored(path):
            continue
        if path.is_file():
            yield path


def _load_package_scripts(root: Path, scan: WorkspaceScan) -> dict[str, str]:
    commands: dict[str, str] = {}
    for package_json in _package_manifests(root, scan):
        try:
            payload = json.loads(package_json.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        scripts = payload.get('scripts')
        if not isinstance(scripts, dict):
            continue
        rel_dir = package_json.parent.relative_to(root)
        prefix = "." if str(rel_dir) == "." else str(rel_dir)
        for key in scripts:
            name = str(key).strip()
            if not name:
                continue
            registry_key = name if prefix == "." else f"{prefix}#{name}"
            commands[registry_key] = f"npm run {name}" if prefix == "." else f"cd {prefix} && npm run {name}"
    return commands


def _detect_ci_workflows(root: Path) -> list[WorkspaceFileHint]:
    workflow_root = root / '.github' / 'workflows'
    if not workflow_root.is_dir():
        return []
    return [WorkspaceFileHint(path=str(path.relative_to(root)), kind='ci_workflow') for path in sorted(workflow_root.glob('*.y*ml'))]


def _detect_entrypoints(root: Path, scripts: dict[str, str]) -> list[WorkspaceEntryPoint]:
    entries: list[WorkspaceEntryPoint] = []
    for candidate, kind in [
        ('src/main.py', 'python_app'),
        ('src/main.ts', 'typescript_app'),
        ('src/main.tsx', 'react_entry'),
        ('src/App.tsx', 'react_app'),
        ('src/copenet/host/frontend/src/main.tsx', 'frontend_entry'),
    ]:
        path = root / candidate
        if path.is_file():
            entries.append(WorkspaceEntryPoint(path=candidate, kind=kind, reason='conventional_entrypoint'))
    for key, command in scripts.items():
        script_name = key.rsplit('#', 1)[-1]
        if script_name in {'dev', 'start'}:
            package_path = 'package.json' if '#' not in key else f"{key.split('#', 1)[0]}/package.json"
            entries.append(WorkspaceEntryPoint(path=package_path, kind='script_entry', reason=f'npm_script:{script_name}:{command}'))
    return entries[:8]


def _detect_subsystems(root: Path, scan: WorkspaceScan) -> list[WorkspaceSubsystem]:
    subsystems: list[WorkspaceSubsystem] = []
    seen: set[str] = set()
    priority = [
        'src/copenet/core/orchestrator',
        'src/copenet/core/harness',
        'src/copenet/core/tools',
        'src/copenet/core/runtime',
        'src/copenet/core/sessions',
        'src/copenet/host/frontend',
        'src/copenet/host',
        'src/copenet/providers',
    ]

    def add_subsystem(candidate: Path, *, fallback_signal: str = 'directory') -> None:
        if not candidate.is_dir() or scan.is_ignored(candidate):
            return
        rel = candidate.relative_to(root).as_posix()
        if rel in seen:
            return
        signals = _subsystem_signals(candidate)
        subsystems.append(WorkspaceSubsystem(name=candidate.name.replace('-', ' '), root=rel, signals=signals or [fallback_signal]))
        seen.add(rel)

    for rel in priority:
        add_subsystem(root / rel)
    for candidate in sorted(path for path in root.iterdir() if path.is_dir() and not scan.is_ignored(path))[:32]:
        signals = _subsystem_signals(candidate)
        if candidate.name in {'src', 'tests', 'docs', 'scripts', 'frontend', 'backend'} or signals:
            add_subsystem(candidate, fallback_signal='top_level')
    return subsystems[:10]


def _subsystem_signals(candidate: Path) -> list[str]:
    signals: list[str] = []
    if (candidate / 'package.json').is_file():
        signals.append('package.json')
    if (candidate / 'pyproject.toml').is_file():
        signals.append('pyproject.toml')
    if list(candidate.glob('*.md')):
        signals.append('docs')
    if any(path.suffix == '.py' for path in candidate.glob('*.py')):
        signals.append('python')
    if any(path.suffix in {'.ts', '.tsx'} for path in candidate.glob('*.ts*')):
        signals.append('typescript')
    return signals


def _detect_verification_commands(root: Path, scan: WorkspaceScan, scripts: dict[str, str]) -> list[VerificationCommand]:
    commands: list[VerificationCommand] = []
    if (root / 'pyproject.toml').is_file() or (root / 'pytest.ini').is_file():
        if _pyproject_declares_dev_extra(root / 'pyproject.toml'):
            commands.append(VerificationCommand(kind='test', command='uv run --extra dev pytest -q', source='python_project:dev_extra', confidence=0.98))
        else:
            commands.append(VerificationCommand(kind='test', command='uv run pytest -q', source='python_project', confidence=0.78))
    seen_commands: set[tuple[str, str]] = set()
    for key, command in scripts.items():
        script_name = key.rsplit('#', 1)[-1]
        source = f'package.json:{key}'
        if script_name == 'test':
            row = VerificationCommand(kind='test', command=command, source=source, confidence=0.95)
        elif script_name == 'lint':
            row = VerificationCommand(kind='lint', command=command, source=source, confidence=0.94)
        elif script_name == 'build':
            row = VerificationCommand(kind='build', command=command, source=source, confidence=0.93)
        elif script_name == 'typecheck':
            row = VerificationCommand(kind='typecheck', command=command, source=source, confidence=0.92)
        else:
            continue
        signature = (row.kind, row.command)
        if signature not in seen_commands:
            seen_commands.add(signature)
            commands.append(row)
    if _package_manifests(root, scan) and not any(command.kind == 'build' for command in commands):
        manifest = _package_manifests(root, scan)[0]
        rel_dir = manifest.parent.relative_to(root)
        command = 'npm run build' if str(rel_dir) == '.' else f"cd {rel_dir} && npm run build"
        commands.append(VerificationCommand(kind='smoke', command=command, source=f'package.json:{manifest.relative_to(root)}', confidence=0.55))
    return commands


def _pyproject_declares_dev_extra(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        return False
    return bool(re.search(r'(?ms)^\[project\.optional-dependencies\]\s*(?:\n[^\[]*)?\n\s*dev\s*=', text))


def _package_manifests(root: Path, scan: WorkspaceScan) -> list[Path]:
    manifests: list[Path] = []
    for path in _iter_named_files(root, 'package.json', scan):
        manifests.append(path)
    return manifests[:8]


def _iter_named_files(root: Path, name: str, scan: WorkspaceScan | None = None) -> Iterable[Path]:
    active_scan = scan or WorkspaceScan(root)
    yield from active_scan.named_files(name)
