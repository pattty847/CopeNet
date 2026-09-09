"""Home: the operator's desk view.

Home is not a subsystem of its own — it owns no data. It is a *reading* of what the market,
session, and run stores already hold, assembled server-side so the page costs one round trip
instead of one per session. The only thing here that is genuinely Home's own is the focus
list: a checklist and a notes pad that belong to the operator rather than to any run.
"""

from copenet.core.home.desk import DeskSnapshot, build_desk_snapshot
from copenet.core.home.focus import FocusStore

__all__ = ["DeskSnapshot", "FocusStore", "build_desk_snapshot"]
