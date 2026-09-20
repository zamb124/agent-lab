"""TaskIQ tasks infrastructure — единый публичный API платформы.

Объявление задачи:
    from core.tasks import declare_task, platform_task

    MY_TASK = declare_task("my_task", queue="idle")

    @platform_task(MY_TASK)
    async def my_task(...) -> None: ...

Постановка в очередь (откуда угодно):
    from core.tasks import enqueue
    await enqueue(MY_TASK, param="value")
"""

from core.tasks.broker import resolve_broker_for_task
from core.tasks.kicker import enqueue
from core.tasks.log_labels import build_log_labels
from core.tasks.registry import (
    TaskPriority,
    TaskSpec,
    all_task_specs,
    declare_task,
    get_task_spec,
    platform_task,
    register_queue_broker,
    registered_queue_brokers,
    scheduled_task_specs,
)
from core.tasks.session_lock import SessionLockMiddleware, session_lock_middleware

__all__ = [
    "SessionLockMiddleware",
    "TaskPriority",
    "TaskSpec",
    "all_task_specs",
    "build_log_labels",
    "declare_task",
    "enqueue",
    "get_task_spec",
    "platform_task",
    "register_queue_broker",
    "registered_queue_brokers",
    "resolve_broker_for_task",
    "scheduled_task_specs",
    "session_lock_middleware",
]
