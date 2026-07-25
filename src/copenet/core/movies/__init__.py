"""Personal Movie Lab: watched-history import, TMDB enrichment, and recommendations."""

from .service import MovieLabService
from .store import MovieLabStore
from .tmdb import TmdbClient, TmdbError

__all__ = ["MovieLabService", "MovieLabStore", "TmdbClient", "TmdbError"]
