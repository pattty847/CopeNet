"""USER.md proposal subsystem — model-proposed identity deltas the operator reviews."""

from .service import DEFAULT_DAILY_LIMIT, UserNoteLimitReached, UserNotesService
from .store import UserNoteProposal, UserNotesStore

__all__ = [
    "DEFAULT_DAILY_LIMIT",
    "UserNoteLimitReached",
    "UserNoteProposal",
    "UserNotesService",
    "UserNotesStore",
]
