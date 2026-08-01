"""Observability facade: settings and evidence for one durable run."""

from __future__ import annotations


class ObservabilityFacadeMixin:
    """Expose operator observability operations without growing Orchestrator."""

    def get_observability_settings(self) -> dict:
        return self._observability_store.load_settings().to_public_dict()

    def update_observability_settings(self, *, debug_capture: bool) -> dict:
        return self._observability_store.update_settings(debug_capture=debug_capture).to_public_dict()

    def resolve_observability_run(self, session_key: str, run_id: str) -> dict | None:
        run = self.resolve_session_run(session_key, run_id)
        if run is None:
            return None
        messages = [
            message
            for message in self.history(session_key, limit=1_000)
            if str(message.get("runId") or "") == run_id
        ]
        events = self._observability_store.list_trace_events(run_id)
        artifacts = [
            artifact
            for artifact in self.list_session_artifacts(session_key, limit=500)
            if str(artifact.get("runId") or "") == run_id
        ]
        return {
            "run": run,
            "messages": messages,
            "events": events,
            "artifacts": artifacts,
            "debugCaptured": bool(events),
        }
