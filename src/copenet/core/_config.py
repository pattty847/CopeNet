"""Process-wide config flags for the CopeNet harness.

Per HARNESS_REBUILD_V2.md Phase 0.4, several auto-mutation features need to
be runtime-toggleable while the harness rebuild is in flight. Default OFF.
Set the env var to one of the truthy strings (1/true/yes/on, case-insensitive)
to enable.

Naming convention follows the existing COPNET_ prefix in this codebase
(see `core/orchestrator/__init__.py` for COPNET_WORKDIR, COPNET_DATA_DIR, etc.).
"""

from __future__ import annotations

import os


_TRUTHY = {"1", "true", "yes", "on"}


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def auto_memory_extraction_enabled() -> bool:
    """Whether to run memory_service.extract_from_run after each chat turn.

    Off by default. Keyword-based extraction of "i like / do not / we should"
    triggers from user text pollutes the next-turn prompt and was the source
    of the multiple loops Codex flagged in round-2 review. Re-enable only when
    a thoughtful explicit-opt-in design lands.
    """
    return _env_flag("COPNET_AUTO_MEMORY_EXTRACTION", default=False)


def auto_profile_extraction_enabled() -> bool:
    """Whether to run profile_service.apply_post_run_updates after each chat turn.

    Off by default for the same reason as memory extraction.
    """
    return _env_flag("COPNET_AUTO_PROFILE_EXTRACTION", default=False)
