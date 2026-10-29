"""Единая топология TaskIQ платформы.

Один источник правды: очередь → ``service_name`` брокера и очередь → модули задач.

- ``wire_worker(queue)`` — создаёт брокер очереди через ``create_broker`` и
  импортирует её impl-модули. Вызывается из ``worker.py``.
- ``wire_brokers()`` — брокеры всех очередей (HTTP scheduler API для kick).
- ``wire_all()`` — брокеры и impl-задачи всех очередей (процесс scheduler).

HTTP-продюсеры сюда не заходят: они делают ``enqueue(SPEC, ...)``, где брокер
очереди создаётся kick-only лениво, а SPEC берётся из declaration-модуля
(``apps/<svc>/tasks/task_names.py``, flows — ``apps/flows/src/tasks/task_names.py``,
sync — ``apps/sync/realtime/task_names.py``).
"""

from __future__ import annotations

from taskiq_redis import RedisStreamBroker

from core.tasks.autodiscover import import_task_modules
from core.tasks.broker import create_broker
from core.tasks.registry import queue_broker

_QUEUE_SERVICE: dict[str, str] = {
    "flows_worker": "flows_worker",
    "idle": "idle_worker",
    "a2a_push": "a2a_push_worker",
    "rag": "rag_worker",
    "crm": "crm_worker",
    "crm_summary": "crm_summary_worker",
    "sync": "sync_worker",
    "search": "search_worker",
    "stock": "stock_worker",
}

# push_notification_tasks биндит задачи и idle, и a2a_push: оба брокера
# регистрируются до импорта модуля.
_IMPORT_BROKERS: dict[str, tuple[str, ...]] = {
    "idle": ("idle", "a2a_push"),
    "a2a_push": ("idle", "a2a_push"),
}

_QUEUE_TASK_MODULES: dict[str, tuple[str, ...]] = {
    "flows_worker": ("apps.flows.src.tasks",),
    "idle": ("apps.idle.tasks",),
    "a2a_push": ("apps.idle.tasks.push_notification_tasks",),
    "rag": ("apps.rag.tasks",),
    "crm": (
        "apps.crm.tasks.analysis_tasks",
        "apps.crm.tasks.draft_repair_tasks",
        "apps.crm.tasks.knowledge_import_tasks",
        "apps.crm.tasks.namespace_integration_tasks",
        "apps.crm.tasks.note_markdown_tasks",
        "apps.crm.tasks.reembed_tasks",
        "apps.crm.tasks.scheduled_integration_sync_tasks",
        "apps.crm.tasks.suggest_tasks",
    ),
    "crm_summary": ("apps.crm.tasks.daily_summary_tasks",),
    "sync": ("apps.sync.realtime.tasks", "apps.sync.realtime.notification_tasks"),
    "search": ("apps.search.tasks",),
    "stock": ("apps.stock.tasks",),
}


def _ensure_broker(queue: str) -> RedisStreamBroker:
    if queue not in _QUEUE_SERVICE:
        raise ValueError(f"unknown queue {queue!r}")
    existing = queue_broker(queue)
    if existing is not None:
        if not isinstance(existing, RedisStreamBroker):
            raise RuntimeError(f"queue broker {queue!r} is not RedisStreamBroker")
        return existing
    return create_broker(queue_name=queue, service_name=_QUEUE_SERVICE[queue])


def all_queues() -> tuple[str, ...]:
    return tuple(_QUEUE_SERVICE.keys())


def wire_brokers() -> None:
    """Зарегистрировать брокеры всех очередей (без impl-задач)."""
    for queue in _QUEUE_SERVICE:
        _ = _ensure_broker(queue)


def wire_worker(queue: str) -> RedisStreamBroker:
    """Создать брокер очереди и зарегистрировать её impl-задачи."""
    if queue not in _QUEUE_SERVICE:
        raise ValueError(f"wire_worker: unknown queue {queue!r}")
    for required in _IMPORT_BROKERS.get(queue, (queue,)):
        _ = _ensure_broker(required)
    _ = import_task_modules(_QUEUE_TASK_MODULES[queue])
    return _ensure_broker(queue)


def wire_all() -> None:
    """Зарегистрировать брокеры и impl-задачи всех очередей (scheduler-процесс)."""
    wire_brokers()
    for queue in _QUEUE_TASK_MODULES:
        _ = import_task_modules(_QUEUE_TASK_MODULES[queue])


__all__ = ["all_queues", "wire_all", "wire_brokers", "wire_worker"]
