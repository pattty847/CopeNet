"""Every benchmark task, both families, keyed by id."""

from __future__ import annotations

from benchmarks.coding.repo_tasks import REPO_TASKS
from benchmarks.coding.tasks import FIXTURE_TASKS, Task

TASKS: list[Task] = [*FIXTURE_TASKS, *REPO_TASKS]
TASKS_BY_ID: dict[str, Task] = {task.id: task for task in TASKS}
