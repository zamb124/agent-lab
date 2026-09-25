"""Единая топология TaskIQ платформы.

Один источник правды: очередь → брокер-модуль и очередь → пакеты задач.

- ``wire_worker(queue)`` — импортирует брокер-модуль очереди (регистрирует
  ``queue → broker`` через ``create_broker``) и autodiscover'ит impl-модули этой
  очереди. Вызывается из ``build_worker``.
- ``wire_brokers()`` — только брокеры всех очередей (HTTP scheduler API для kick).
- ``wire_all()`` — брокеры + impl-задачи всех очередей (scheduler-процесс).

HTTP-продюсеры сюда не заходят: они делают ``enqueue(SPEC, ...)``, где брокер
очереди создаётся kick-only лениво, а SPEC берётся из лёгкого
``apps/<svc>_worker/tasks/task_names.py``.
"""

from __future__ import annotations

import importlib

from taskiq_redis import RedisStreamBroker

from core.tasks.autodiscover import import_task_modules
from core.tasks.registry import queue_broker

_QUEUE_BROKER_MODULE: dict[str, str] = {
    "flows_worker": "apps.flows_worker.broker",
    "idle": "apps.idle_worker.broker",
    "a2a_push": "apps.idle_worker.a2a_push_broker",
    "rag": "apps.rag_worker.broker",
    "crm": "apps.crm_worker.broker",
    "crm_summary": "apps.crm_worker.summary_broker",
    "sync": "apps.sync.realtime.broker",
    "search": "apps.search_worker.broker",
}

_QUEUE_TASK_MODULES: dict[str, tuple[str, ...]] = {
    "flows_worker": ("apps.flows.src.tasks", "apps.flows_worker.evaluation_tasks"),
    "idle": ("apps.idle_worker.tasks",),
    "a2a_push": ("apps.idle_worker.tasks.push_notification_tasks",),
    "rag": ("apps.rag_worker.tasks",),
    "crm": (
        "apps.crm_worker.tasks.analysis_tasks",
        "apps.crm_worker.tasks.draft_repair_tasks",
        "apps.crm_worker.tasks.knowledge_import_tasks",
        "apps.crm_worker.tasks.namespace_integration_tasks",
        "apps.crm_worker.tasks.note_markdown_tasks",
        "apps.crm_worker.tasks.reembed_tasks",
        "apps.crm_worker.tasks.scheduled_integration_sync_tasks",
        "apps.crm_worker.tasks.suggest_tasks",
    ),
    "crm_summary": ("apps.crm_worker.tasks.daily_summary_tasks",),
    "sync": ("apps.sync.realtime.tasks", "apps.sync.realtime.notification_tasks"),
    "search": ("apps.search_worker.tasks",),
}


def all_queues() -> tuple[str, ...]:
    return tuple(_QUEUE_BROKER_MODULE.keys())


def wire_brokers() -> None:
    """Зарегистрировать брокеры всех очередей (без impl-задач)."""
    for queue in _QUEUE_BROKER_MODULE:
        _ = importlib.import_module(_QUEUE_BROKER_MODULE[queue])


def wire_worker(queue: str) -> RedisStreamBroker:
    """Импортировать брокер очереди и зарегистрировать её impl-задачи."""
    if queue not in _QUEUE_BROKER_MODULE:
        raise ValueError(f"wire_worker: unknown queue {queue!r}")
    _ = importlib.import_module(_QUEUE_BROKER_MODULE[queue])
    _ = import_task_modules(_QUEUE_TASK_MODULES[queue])
    broker = queue_broker(queue)
    if not isinstance(broker, RedisStreamBroker):
        raise RuntimeError(f"wire_worker: queue broker {queue!r} is not registered")
    return broker


def wire_all() -> None:
    """Зарегистрировать брокеры и impl-задачи всех очередей (scheduler-процесс)."""
    wire_brokers()
    for queue in _QUEUE_TASK_MODULES:
        _ = import_task_modules(_QUEUE_TASK_MODULES[queue])


__all__ = ["all_queues", "wire_all", "wire_brokers", "wire_worker"]
