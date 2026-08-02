"""Observability facade: settings and evidence for one durable run."""

from __future__ import annotations


class ObservabilityFacadeMixin:
    """Expose operator observability operations without growing Orchestrator."""

    def get_observability_settings(self) -> dict:
        return self._observability_settings_payload(self._observability_store.load_settings())

    def update_observability_settings(self, *, debug_capture: bool) -> dict:
        return self._observability_settings_payload(
            self._observability_store.update_settings(debug_capture=debug_capture)
        )

    def purge_observability_traces(self) -> dict:
        """Delete every stored run trace and return the refreshed settings payload."""
        result = self._observability_store.purge_traces()
        payload = self.get_observability_settings()
        payload["purged"] = result
        return payload

    def _observability_settings_payload(self, settings) -> dict:
        payload = settings.to_public_dict()
        payload["traceStorage"] = self._observability_store.trace_storage_stats()
        return payload

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
        # `debugCaptured` means the payload-heavy tier is present, not merely that a
        # trace exists — lifecycle events are written for every run now, so
        # `bool(events)` would report every run as debug-captured.
        return {
            "run": run,
            "messages": messages,
            "events": events,
            "artifacts": artifacts,
            "debugCaptured": any(str(event.get("tier") or "") == "debug" for event in events),
            "lifecycleCaptured": bool(events),
        }
