"""Единая постановка TaskIQ задач в очередь.

Единственный способ поставить задачу — ``enqueue(spec, **payload)``. Он сам
резолвит брокер очереди по ``TaskSpec`` и прикрепляет обязательные лог-метки
(см. ``core.tasks.log_labels.build_log_labels``) и опциональный ``priority``.

``taskiq_task_id`` задаёт TaskIQ ``task_id`` сообщения (evaluation replay).
Имя не ``task_id``: у ``process_flow`` это поле payload.

``enqueue_dynamic`` — тот же путь для kwargs, пришедших из хранилища как
один ``JsonObject`` (continuation/resume A2A): spread такого словаря в
``enqueue`` статически не типизируется, семантика постановки та же.

Прямой TaskIQ kick / find_task вне whitelist запрещён CI-гейтами
(``scripts/gates/backend/taskiq.py``, ``scripts/gates/backend/logging_canon.sh``).
"""

from __future__ import annotations

from taskiq import AsyncTaskiqTask
from taskiq.kicker import AsyncKicker

from core.tasks.broker import resolve_broker_for_task
from core.tasks.log_labels import (
    LABEL_PRIORITY,
    LABEL_QUEUE_NAME,
    build_log_labels,
    merge_extra_labels,
)
from core.tasks.registry import TaskPriority, TaskSpec, get_task_spec
from core.types import JsonObject, JsonValue


async def _enqueue(
    task: TaskSpec | str,
    args: tuple[JsonValue, ...],
    kwargs: JsonObject,
    *,
    priority: TaskPriority | None,
    override_request_id: str | None,
    override_trace_id: str | None,
    service_name: str | None,
    background_kind: str | None,
    extra_labels: dict[str, str] | None,
    taskiq_task_id: str | None,
) -> AsyncTaskiqTask[JsonValue]:
    if taskiq_task_id is not None and not taskiq_task_id.strip():
        raise ValueError('enqueue: taskiq_task_id is empty')
    spec = get_task_spec(task)
    broker = resolve_broker_for_task(spec)
    labels = build_log_labels(
        override_request_id=override_request_id,
        override_trace_id=override_trace_id,
        service_name=service_name,
        background_kind=background_kind,
    )
    labels[LABEL_QUEUE_NAME] = spec.queue
    if priority is not None:
        labels[LABEL_PRIORITY] = str(int(priority))
    merge_extra_labels(labels, extra_labels)
    kicker: AsyncKicker[..., JsonValue] = AsyncKicker(spec.name, broker, labels)
    if taskiq_task_id is not None:
        kicker = kicker.with_task_id(taskiq_task_id)
    return await kicker.kiq(*args, **kwargs)


async def enqueue(
    task: TaskSpec | str,
    *args: JsonValue,
    priority: TaskPriority | None = None,
    override_request_id: str | None = None,
    override_trace_id: str | None = None,
    service_name: str | None = None,
    background_kind: str | None = None,
    extra_labels: dict[str, str] | None = None,
    taskiq_task_id: str | None = None,
    **kwargs: JsonValue,
) -> AsyncTaskiqTask[JsonValue]:
    """Единственный способ поставить задачу в очередь.

    ``task`` — ``TaskSpec`` (или её имя, если declaration-модуль уже импортирован).
    Брокер очереди резолвится автоматически; в producer-процессе создаётся
    kick-only брокер очереди лениво.
    """
    return await _enqueue(
        task,
        args,
        kwargs,
        priority=priority,
        override_request_id=override_request_id,
        override_trace_id=override_trace_id,
        service_name=service_name,
        background_kind=background_kind,
        extra_labels=extra_labels,
        taskiq_task_id=taskiq_task_id,
    )


async def enqueue_dynamic(
    task: TaskSpec | str,
    kwargs: JsonObject,
) -> AsyncTaskiqTask[JsonValue]:
    """``enqueue`` для kwargs из хранилища: весь payload одним ``JsonObject``.

    Используется там, где набор kwargs определён ранее и сохранён целиком
    (continuation-задачи A2A): статический вызов ``enqueue(spec, **row)``
    не типизируется, а семантика постановки идентична.
    """
    return await _enqueue(
        task,
        (),
        kwargs,
        priority=None,
        override_request_id=None,
        override_trace_id=None,
        service_name=None,
        background_kind=None,
        extra_labels=None,
        taskiq_task_id=None,
    )


__all__ = [
    "enqueue",
    "enqueue_dynamic",
]
