"""Хелперы для тестов постановки TaskIQ-задач через ``enqueue``."""

from __future__ import annotations

from core.tasks import TaskSpec


def taskiq_task_name(task: TaskSpec | str) -> str:
    """Имя задачи из ``TaskSpec`` или строки (как передаёт ``enqueue``)."""
    if isinstance(task, TaskSpec):
        return task.name
    if task.strip():
        return task.strip()
    raise TypeError("ожидался непустой TaskSpec | str")
