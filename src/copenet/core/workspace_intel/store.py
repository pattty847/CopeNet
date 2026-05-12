"""Durable workspace intelligence cache store."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from .models import WorkspaceEntryPoint, WorkspaceFileHint, WorkspaceIntelRecord, WorkspaceSubsystem, VerificationCommand


class WorkspaceIntelStore:
    """Durable local cache keyed by workspace root."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def get(self, workspace_root: str) -> WorkspaceIntelRecord | None:
        payload = self._read_all().get(workspace_root)
        if not isinstance(payload, dict):
            return None
        return _record_from_dict(payload)

    def save(self, record: WorkspaceIntelRecord) -> None:
        data = self._read_all()
        data[record.workspace_root] = _record_to_dict(record)
        self._write_all(data)

    def _read_all(self) -> dict[str, object]:
        if not self._path.is_file():
            return {}
        try:
            payload = json.loads(self._path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_all(self, payload: dict[str, object]) -> None:
        tmp_path = self._path.with_suffix(f'{self._path.suffix}.tmp')
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        tmp_path.replace(self._path)


def _record_to_dict(record: WorkspaceIntelRecord) -> dict[str, object]:
    payload = asdict(record)
    return payload


def _record_from_dict(payload: dict[str, object]) -> WorkspaceIntelRecord:
    return WorkspaceIntelRecord(
        workspace_root=str(payload.get('workspace_root') or ''),
        fingerprint=str(payload.get('fingerprint') or ''),
        schema_version=int(payload.get('schema_version') or 1),
        top_level_paths=[str(item) for item in payload.get('top_level_paths') or []],
        languages=[str(item) for item in payload.get('languages') or []],
        package_managers=[str(item) for item in payload.get('package_managers') or []],
        config_files=[WorkspaceFileHint(**item) for item in payload.get('config_files') or []],
        scripts={str(key): str(value) for key, value in dict(payload.get('scripts') or {}).items()},
        ci_workflows=[WorkspaceFileHint(**item) for item in payload.get('ci_workflows') or []],
        entrypoints=[WorkspaceEntryPoint(**item) for item in payload.get('entrypoints') or []],
        subsystems=[WorkspaceSubsystem(**item) for item in payload.get('subsystems') or []],
        verification_hints=[VerificationCommand(**item) for item in payload.get('verification_hints') or []],
        recommended_default_checks=[str(item) for item in payload.get('recommended_default_checks') or []],
        generated_at=str(payload.get('generated_at') or ''),
    )
