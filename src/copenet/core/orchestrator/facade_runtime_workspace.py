"""Runtime context, workspace file, artifact, and run facade methods."""

from __future__ import annotations

import subprocess
from pathlib import Path

from copenet.core.orchestrator.merge import resolve_merge_state as resolve_merge_state_record


class RuntimeWorkspaceFacadeMixin:
    def validate_workspace_root(self, workspace_root: str | None) -> str:
        """Validate and normalize one session workspace root."""
        candidate = Path((workspace_root or "").strip() or str(self._workdir)).expanduser().resolve()
        if not candidate.exists():
            raise ValueError(f"workspace root not found: {candidate}")
        if not candidate.is_dir():
            raise ValueError(f"workspace root is not a directory: {candidate}")
        return str(candidate)

    def browse_workspace_root(self) -> str | None:
        """Open a macOS-native folder picker and return the chosen path."""
        script = 'set chosenFolder to choose folder with prompt "Choose CopeNet workspace root"\nPOSIX path of chosenFolder'
        try:
            completed = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("native folder picker unavailable: osascript not found") from exc
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            if "User canceled" in stderr:
                return None
            raise RuntimeError(stderr or "native folder picker failed")
        selected = (completed.stdout or "").strip()
        return self.validate_workspace_root(selected) if selected else None

    def get_runtime_context(
        self,
        *,
        session_key: str | None = None,
        workspace_root: str | None = None,
    ) -> dict:
        """Return the current workspace root and access-policy summary."""
        selected_root = workspace_root
        if session_key:
            entry = self._session_store.get(session_key.strip())
            if entry is not None and entry.workspace_root:
                selected_root = entry.workspace_root
        resolved_root = self.validate_workspace_root(selected_root) if selected_root else str(self._workdir)
        return {
            "workspaceRoot": resolved_root,
            "fileToolScope": "workspace_home_visible_roaming",
            "shellToolScope": "cwd_default",
            "shellAllowlist": list(self._tool_policy.shell_allowlist),
            "workspaceIntel": self._workspace_intel_service.get_summary(resolved_root),
            "note": (
                "Repo/file tools default to this home workspace. Reads outside it are allowed but should be visibly marked. "
                "Allowlisted shell commands run from this root."
            ),
        }

    def resolve_session_state(self, session_key: str) -> dict | None:
        """Resolve one structured runtime state record for a session."""
        record = self._session_state_store.get(session_key.strip())
        return record.to_json() if record is not None else None

    def resolve_merge_state(self, session_key: str) -> dict[str, object] | None:
        """Resolve one persisted merge-state payload for a merged session."""
        return resolve_merge_state_record(self, session_key)

    def list_session_artifacts(self, session_key: str, limit: int = 50) -> list[dict]:
        """List recent durable artifacts for one session."""
        return [record.to_public_dict() for record in self._artifact_store.list_for_session(session_key.strip(), limit=limit)]

    def _resolve_session_workspace_root(self, session_key: str) -> Path:
        """Return the on-disk workspace root for a session (falls back to workdir)."""
        entry = self._session_store.get(session_key.strip())
        selected_root = entry.workspace_root if entry is not None and entry.workspace_root else None
        return Path(self.validate_workspace_root(selected_root) if selected_root else str(self._workdir))

    def list_session_workspace_files(self, *, session_key: str) -> dict:
        """List viewable files under a session's workspace root (read-only viewer)."""
        from copenet.core.workspace_files import list_workspace_files

        root = self._resolve_session_workspace_root(session_key)
        return {"root": str(root), "files": list_workspace_files(root)}

    def read_session_workspace_file(self, *, session_key: str, path: str) -> dict:
        """Read one file under a session's workspace root (scoped, size-capped)."""
        from copenet.core.workspace_files import read_workspace_file

        root = self._resolve_session_workspace_root(session_key)
        return read_workspace_file(root, path)

    def write_session_workspace_file(self, *, session_key: str, path: str, content: str) -> dict:
        """Operator inline-edit: write a file under a session's workspace root.

        Records a pre-edit backup keyed by the new content's digest so the change
        is revertible through the same `revert_file_edit` path as a model edit.
        """
        import hashlib
        from copenet.core.workspace_files import write_workspace_file

        root = self._resolve_session_workspace_root(session_key)
        result = write_workspace_file(root, path, content)
        before_content = result.pop("beforeContent", "")
        existed = result.pop("existed", False)
        after_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        if existed:
            self._edit_backup_store.record(
                session_key=session_key.strip(),
                path=result["path"],
                after_digest=after_digest,
                before_content=before_content,
            )
        result["digest"] = after_digest
        result["revertible"] = existed
        return result

    def _persona_root_rel(self, path: str) -> tuple[Path, str]:
        """Validate an absolute persona file path is under the persona root.

        Persona ``loadedFiles`` are absolute paths under the persona root; returns
        (root, rel_path) for reuse with the workspace file read/write helpers.
        """
        root = Path(self._persona_service.root_dir).resolve()
        candidate = Path((path or "").strip()).expanduser().resolve()
        try:
            rel = str(candidate.relative_to(root))
        except ValueError as exc:
            raise ValueError("path is outside the persona root") from exc
        return root, rel

    def read_persona_file(self, *, path: str) -> dict:
        """Read one persona file (scoped to the persona root, size-capped)."""
        from copenet.core.workspace_files import read_workspace_file

        root, rel = self._persona_root_rel(path)
        return read_workspace_file(root, rel)

    def write_persona_file(self, *, path: str, content: str) -> dict:
        """Operator inline-edit of a persona file (scoped to the persona root).

        Records a pre-edit backup under a persona-scoped key so the change is
        revertible through the same machinery as workspace edits.
        """
        import hashlib
        from copenet.core.workspace_files import write_workspace_file

        root, rel = self._persona_root_rel(path)
        result = write_workspace_file(root, rel, content)
        before_content = result.pop("beforeContent", "")
        existed = result.pop("existed", False)
        after_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        if existed:
            self._edit_backup_store.record(
                session_key="__persona__",
                path=rel,
                after_digest=after_digest,
                before_content=before_content,
            )
        result["digest"] = after_digest
        result["revertible"] = existed
        return result

    def revert_file_edit(self, *, session_key: str, path: str, after_digest: str) -> dict:
        """Undo a model's write/edit by restoring the recorded pre-edit content.

        Operator-initiated (not a model tool), keyed by (session_key, path,
        after_digest). Refuses unless the file is still in the exact state the
        edit left it, so a newer change is never silently clobbered.
        """
        import hashlib

        session_key = session_key.strip()
        rel_path = path.strip()
        after_digest = after_digest.strip()
        if not session_key or not rel_path or not after_digest:
            return {"ok": False, "error": "session_key, path, and after_digest are required"}

        entry = self._session_store.get(session_key)
        selected_root = entry.workspace_root if entry is not None and entry.workspace_root else None
        root = Path(self.validate_workspace_root(selected_root) if selected_root else str(self._workdir))
        target = (root / rel_path).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            return {"ok": False, "error": "path is outside the session workspace"}
        if not target.is_file():
            return {"ok": False, "error": f"file not found: {rel_path}"}

        current = target.read_text(encoding="utf-8", errors="replace")
        current_digest = hashlib.sha256(current.encode("utf-8")).hexdigest()[:16]
        if current_digest != after_digest:
            return {
                "ok": False,
                "error": "file changed since this edit; not reverting",
                "path": rel_path,
            }

        record = self._edit_backup_store.find(session_key=session_key, path=rel_path, after_digest=after_digest)
        if record is None:
            return {"ok": False, "error": "no backup found for this edit", "path": rel_path}

        target.write_text(record.before_content, encoding="utf-8")
        self._edit_backup_store.mark_reverted(session_key=session_key, path=rel_path, after_digest=after_digest)
        new_digest = hashlib.sha256(record.before_content.encode("utf-8")).hexdigest()[:16]
        return {"ok": True, "path": rel_path, "newDigest": new_digest}

    def list_session_runs(self, session_key: str, limit: int = 50) -> list[dict]:
        """List recent durable run records for one session."""
        return [record.to_public_dict() for record in self._run_store.list_for_session(session_key.strip(), limit=limit)]

    def resolve_session_run(self, session_key: str, run_id: str) -> dict | None:
        """Resolve one durable run record for a session."""
        record = self._run_store.get(session_key.strip(), run_id.strip())
        return record.to_public_dict() if record is not None else None
