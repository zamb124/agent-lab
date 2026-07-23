"""Единый реестр TaskIQ задач платформы.

Один источник правды для всех задач: имя, очередь, признак scheduled, retry.

Два plain-dict реестра (core не импортирует apps):
- ``_TASK_SPECS``: ``name -> TaskSpec`` — заполняется ``declare_task`` в лёгких
  declaration-модулях (``apps/<svc>_worker/tasks/task_names.py``).
- ``_QUEUE_BROKERS``: ``queue -> AsyncBroker`` — заполняется ``create_broker``
  (``core.tasks.broker``) при создании брокера очереди.

Единственный способ объявить задачу — ``@platform_task(spec)``; прямой
декоратор ``broker.task`` в ``apps/**`` запрещён CI-гейтом
``scripts/check_taskiq_canon.py``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from typing import ParamSpec, TypeVar

from taskiq import AsyncBroker, AsyncTaskiqDecoratedTask

_TASK_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

_TaskParams = ParamSpec("_TaskParams")
_TaskReturn = TypeVar("_TaskReturn")


class TaskPriority(IntEnum):
    """Приоритет задачи (меньше — выше). Хук для будущих priority-bands.

    Сейчас пишется только в label ``priority`` для observability и не меняет
    маршрутизацию/топологию очередей.
    """

    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4
    LOWEST = 5


@dataclass(frozen=True, slots=True)
class TaskSpec:
    """Каноническое объявление задачи: имя, очередь, поведение."""

    name: str
    queue: str
    scheduled: bool = False
    retry: bool = False
    max_retries: int = 3


_TASK_SPECS: dict[str, TaskSpec] = {}
_QUEUE_BROKERS: dict[str, AsyncBroker] = {}


def declare_task(
    name: str,
    *,
    queue: str,
    scheduled: bool = False,
    retry: bool = False,
    max_retries: int = 3,
) -> TaskSpec:
    """Объявить задачу. Идемпотентно при полном совпадении полей.

    Имя обязано быть snake_case и глобально уникальным (Zero-Guess: конфликт → raise).
    """
    if not _TASK_NAME_RE.match(name):
        raise ValueError(f"declare_task: имя {name!r} должно быть snake_case (^[a-z][a-z0-9_]*$)")
    if not queue.strip():
        raise ValueError(f"declare_task: queue обязателен для задачи {name!r}")
    if max_retries < 1:
        raise ValueError(f"declare_task: max_retries >= 1 для задачи {name!r}")
    spec = TaskSpec(
        name=name,
        queue=queue.strip(),
        scheduled=scheduled,
        retry=retry,
        max_retries=max_retries,
    )
    existing = _TASK_SPECS.get(name)
    if existing is not None:
        if existing != spec:
            raise ValueError(f"declare_task: {name!r} уже объявлена иначе: {existing} != {spec}")
        return existing
    _TASK_SPECS[name] = spec
    return spec


def register_queue_broker(queue: str, broker: AsyncBroker) -> None:
    """Зарегистрировать брокер очереди для резолва enqueue."""
    if not queue.strip():
        raise ValueError("register_queue_broker: queue обязателен")
    _QUEUE_BROKERS[queue.strip()] = broker


def queue_broker(queue: str) -> AsyncBroker | None:
    return _QUEUE_BROKERS.get(queue)


def get_task_spec(task: TaskSpec | str) -> TaskSpec:
    if isinstance(task, TaskSpec):
        registered = _TASK_SPECS.get(task.name)
        if registered is None:
            raise ValueError(
                f"get_task_spec: TaskSpec {task.name!r} не в реестре "
                + "(импортируйте declaration-модуль / не собирайте TaskSpec вручную)"
            )
        if registered != task:
            raise ValueError(
                f"get_task_spec: orphan/wrong-queue TaskSpec {task!r}, "
                + f"в реестре {registered!r}"
            )
        return registered
    spec = _TASK_SPECS.get(task)
    if spec is None:
        raise ValueError(
            f"get_task_spec: задача {task!r} не объявлена (импортируйте её declaration-модуль)"
        )
    return spec


def all_task_specs() -> tuple[TaskSpec, ...]:
    return tuple(_TASK_SPECS.values())


def scheduled_task_specs() -> tuple[TaskSpec, ...]:
    return tuple(spec for spec in _TASK_SPECS.values() if spec.scheduled)


def registered_queue_brokers() -> dict[str, AsyncBroker]:
    return dict(_QUEUE_BROKERS)


def platform_task(
    task: TaskSpec,
) -> Callable[
    [Callable[_TaskParams, _TaskReturn]],
    AsyncTaskiqDecoratedTask[_TaskParams, _TaskReturn],
]:
    """Единственный способ объявить исполнителя задачи.

    Биндит функцию к реальному брокеру очереди (broker должен быть зарегистрирован
    через ``create_broker`` до импорта impl-модуля — гарантируется порядком в
    ``apps/platform_tasks/wiring.py``: сначала брокеры, затем autodiscover).
    Проставляет ``queue_name`` label (нужен scheduler dispatch и kick-роутингу).
    """
    broker = _QUEUE_BROKERS.get(task.queue)
    if broker is None:
        msg = f"platform_task: брокер очереди {task.queue!r} не зарегистрирован"
        raise RuntimeError(f"{msg}; импортируйте брокер-модуль до impl (apps/platform_tasks/wiring)")
    return broker.task(
        task_name=task.name,
        queue_name=task.queue,
        retry_on_error=task.retry,
        max_retries=task.max_retries,
    )


__all__ = [
    "TaskPriority",
    "TaskSpec",
    "all_task_specs",
    "declare_task",
    "get_task_spec",
    "platform_task",
    "queue_broker",
    "register_queue_broker",
    "registered_queue_brokers",
    "scheduled_task_specs",
]
