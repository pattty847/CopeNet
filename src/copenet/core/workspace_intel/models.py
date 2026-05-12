"""Workspace intelligence cache models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

WorkspaceCacheStatus = Literal['cached', 'fresh', 'refreshed', 'stale']
CommandKind = Literal['test', 'lint', 'build', 'typecheck', 'smoke']


@dataclass(frozen=True)
class WorkspaceFileHint:
    path: str
    kind: str

    def to_public_dict(self) -> dict[str, str]:
        return {'path': self.path, 'kind': self.kind}


@dataclass(frozen=True)
class WorkspaceEntryPoint:
    path: str
    kind: str
    reason: str

    def to_public_dict(self) -> dict[str, str]:
        return {'path': self.path, 'kind': self.kind, 'reason': self.reason}


@dataclass(frozen=True)
class WorkspaceSubsystem:
    name: str
    root: str
    signals: list[str] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, object]:
        return {'name': self.name, 'root': self.root, 'signals': list(self.signals)}


@dataclass(frozen=True)
class VerificationCommand:
    kind: CommandKind
    command: str
    source: str
    confidence: float

    def to_public_dict(self) -> dict[str, object]:
        return {
            'kind': self.kind,
            'command': self.command,
            'source': self.source,
            'confidence': round(float(self.confidence), 2),
        }


@dataclass(frozen=True)
class WorkspaceIntelRecord:
    workspace_root: str
    fingerprint: str
    schema_version: int = 1
    top_level_paths: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    config_files: list[WorkspaceFileHint] = field(default_factory=list)
    scripts: dict[str, str] = field(default_factory=dict)
    ci_workflows: list[WorkspaceFileHint] = field(default_factory=list)
    entrypoints: list[WorkspaceEntryPoint] = field(default_factory=list)
    subsystems: list[WorkspaceSubsystem] = field(default_factory=list)
    verification_hints: list[VerificationCommand] = field(default_factory=list)
    recommended_default_checks: list[str] = field(default_factory=list)
    generated_at: str = ''

    def to_public_dict(self, *, cache_status: WorkspaceCacheStatus) -> dict[str, object]:
        return {
            'workspaceRoot': self.workspace_root,
            'cacheStatus': cache_status,
            'topLevelPaths': list(self.top_level_paths),
            'languages': list(self.languages),
            'packageManagers': list(self.package_managers),
            'configFiles': [item.to_public_dict() for item in self.config_files],
            'scripts': dict(self.scripts),
            'ciWorkflows': [item.to_public_dict() for item in self.ci_workflows],
            'entrypoints': [item.to_public_dict() for item in self.entrypoints],
            'subsystems': [item.to_public_dict() for item in self.subsystems],
            'verificationHints': [item.to_public_dict() for item in self.verification_hints],
            'recommendedDefaultChecks': list(self.recommended_default_checks),
            'generatedAt': self.generated_at,
        }

    def to_test_discovery_dict(self, *, cache_status: WorkspaceCacheStatus) -> dict[str, object]:
        return {
            'workspaceRoot': self.workspace_root,
            'cacheStatus': cache_status,
            'commands': [item.to_public_dict() for item in self.verification_hints],
            'recommendedDefaultChecks': list(self.recommended_default_checks),
            'generatedAt': self.generated_at,
        }
