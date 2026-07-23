"""Единая постановка TaskIQ задач в очередь.

Единственный способ поставить задачу — ``enqueue(spec, **payload)``. Он сам
резолвит брокер очереди по ``TaskSpec`` и прикрепляет обязательные лог-метки
(см. ``core.tasks.log_labels.build_log_labels``) и опциональный ``priority``.

Прямой TaskIQ kick / find_task вне whitelist запрещён CI-гейтами
(``scripts/check_taskiq_canon.py``, ``scripts/check_logging_canon.sh``).

``kicker_for_task_name_with_log_labels`` оставлен только для редкого сценария с
``.with_task_id(...)`` (evaluation replay).
"""

from __future__ import annotations

from taskiq import AsyncBroker, AsyncTaskiqTask
from taskiq.kicker import AsyncKicker

from core.tasks.broker import resolve_broker_for_task
from core.tasks.log_labels import (
    LABEL_PRIORITY,
    LABEL_QUEUE_NAME,
    build_log_labels,
    merge_extra_labels,
)
from core.tasks.registry import TaskPriority, TaskSpec, get_task_spec
from core.types import JsonValue


async def enqueue(
    task: TaskSpec | str,
    *args: JsonValue,
    priority: TaskPriority | None = None,
    override_request_id: str | None = None,
    override_trace_id: str | None = None,
    service_name: str | None = None,
    background_kind: str | None = None,
    extra_labels: dict[str, str] | None = None,
    **kwargs: JsonValue,
) -> AsyncTaskiqTask[JsonValue]:
    """Единственный способ поставить задачу в очередь.

    ``task`` — ``TaskSpec`` (или её имя, если declaration-модуль уже импортирован).
    Брокер очереди резолвится автоматически; в producer-процессе создаётся
    kick-only брокер очереди лениво.
    """
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
    return await kicker.kiq(*args, **kwargs)


def kicker_for_task_name_with_log_labels(
    task_name: str,
    broker: AsyncBroker,
    *,
    override_request_id: str | None = None,
    override_trace_id: str | None = None,
    service_name: str | None = None,
    background_kind: str | None = None,
    extra_labels: dict[str, str] | None = None,
) -> AsyncKicker[..., JsonValue]:
    """AsyncKicker с лог-метками для сценария с ``.with_task_id(...)`` (evaluation)."""
    if not task_name.strip():
        raise ValueError("kicker_for_task_name_with_log_labels: task_name пустой")
    labels = build_log_labels(
        override_request_id=override_request_id,
        override_trace_id=override_trace_id,
        service_name=service_name,
        background_kind=background_kind,
    )
    merge_extra_labels(labels, extra_labels)
    return AsyncKicker(task_name.strip(), broker, labels)


__all__ = [
    "enqueue",
    "kicker_for_task_name_with_log_labels",
]
