"""Shared primitives for running isolated, tool-enabled provider lanes.

Used by Fleet's dual-model rooms (core/fleet/) and Research Lab's dual-analyst
stages. Neither owns this module; both depend on it.
"""

from .lane_runner import LaneTurnSpec, create_lane_sessions, render_event_block, run_lane_turn, select_lane_updates

__all__ = [
    "LaneTurnSpec",
    "create_lane_sessions",
    "render_event_block",
    "run_lane_turn",
    "select_lane_updates",
]
