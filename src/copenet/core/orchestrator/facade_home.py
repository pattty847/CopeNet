"""Home facade: the desk snapshot and the operator's focus list."""

from __future__ import annotations

from copenet.core.home.desk import build_desk_snapshot
from copenet.core.home.quotes import quote_for


class HomeFacadeMixin:
    """Expose the desk view without growing Orchestrator."""

    def desk_snapshot(self, *, activity_limit: int = 8) -> dict:
        """One round trip for the whole Home page.

        Deliberately server-side: "what ran lately" is a question across every session, and
        the client can only ask one session at a time — this workspace has hundreds, so the
        fan-out version is not a page load, it is a denial of service against your own host.
        """
        entries = self._session_store.list_sessions(include_archived=False)
        titles = {entry.session_key: (entry.title or entry.session_key) for entry in entries}
        in_flight = sum(1 for entry in entries if entry.in_flight_run_id)
        runs = self._run_store.list_recent_across_sessions(limit=60)
        snapshot = build_desk_snapshot(
            runs=runs,
            session_titles=titles,
            total_sessions=len(entries),
            in_flight=in_flight,
            quote=quote_for(),
            activity_limit=activity_limit,
        )
        return snapshot.to_public_dict()

    # ---------------------------------------------------------------- focus list

    def get_focus(self) -> dict:
        return self._focus_store.load().to_public_dict()

    def add_focus_item(self, text: str) -> dict:
        return self._focus_store.add_item(text).to_public_dict()

    def set_focus_item(self, item_id: str, *, text: str | None = None, done: bool | None = None) -> dict:
        return self._focus_store.set_item(item_id, text=text, done=done).to_public_dict()

    def remove_focus_item(self, item_id: str) -> dict:
        return self._focus_store.remove_item(item_id).to_public_dict()

    def clear_done_focus_items(self) -> dict:
        return self._focus_store.clear_done().to_public_dict()

    def set_focus_notes(self, notes: str) -> dict:
        return self._focus_store.set_notes(notes).to_public_dict()

    def set_quick_launch(self, tiles: list[str]) -> dict:
        return self._focus_store.set_quick_launch(tiles).to_public_dict()
