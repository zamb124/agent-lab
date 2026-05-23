"""
Хелперы для постановки TaskIQ задач с обязательными лог-метками.

Каждая постановка задачи в очередь обязана нести labels:
- ``request_id`` — сквозной идентификатор запроса (HTTP/WS, scheduler, background).
- ``trace_id`` — OTel trace_id или платформенная альтернатива.
- ``service_name`` — кто инициировал постановку (frontend, crm, sync, scheduler...).

Кроме того опционально передаются user_id, company_id, namespace, session_id —
для авторизованных задач.

Использование:

    from core.tasks.kicker import kiq_with_context

    await kiq_with_context(my_task, payload)              # из request scope
    await kiq_with_context(my_task, payload,
                           override_request_id="background:" + uuid.uuid4().hex)

Это единственный поддерживаемый способ kiq() в платформе. Прямой ``my_task.kiq(...)``
без log labels запрещён CI-проверкой ``scripts/check_logging_canon.sh``.
"""

from __future__ import annotations

import uuid

from taskiq import AsyncBroker, AsyncTaskiqDecoratedTask, AsyncTaskiqTask
from taskiq.kicker import AsyncKicker

from core.config import get_settings
from core.logging import get_log_context
from core.types import JsonValue

_LABEL_REQUEST_ID = "request_id"
_LABEL_TRACE_ID = "trace_id"
_LABEL_SERVICE_NAME = "service_name"
_LABEL_USER_ID = "user_id"
_LABEL_COMPANY_ID = "company_id"
_LABEL_NAMESPACE = "namespace"
_LABEL_SESSION_ID = "session_id"


def build_log_labels(
    *,
    override_request_id: str | None = None,
    override_trace_id: str | None = None,
    service_name: str | None = None,
    background_kind: str | None = None,
) -> dict[str, str]:
    """
    Собрать labels для kiq(): тащит request_id/trace_id/user_id из лог-контекста.

    Если контекст пуст и явных override нет — генерируется фоновый identifier
    с префиксом из ``background_kind`` (например ``cron``, ``sched``,
    ``startup``). Это допустимо только для системных triggerов; HTTP/WS
    handlers всегда работают внутри request scope, где request_id уже есть.

    Raises:
        ValueError: если override_request_id/override_trace_id явно пустые
            строки (а не None).
    """
    log_ctx = get_log_context()
    settings = get_settings()
    effective_service = (service_name or settings.server.name).strip()
    if not effective_service:
        raise ValueError("build_log_labels: service_name не определён")

    request_id = _resolve_id(
        override_request_id,
        log_ctx.get(_LABEL_REQUEST_ID),
        background_kind=background_kind,
    )
    trace_id = _resolve_id(
        override_trace_id,
        log_ctx.get(_LABEL_TRACE_ID),
        background_kind=background_kind,
    )

    labels: dict[str, str] = {
        _LABEL_REQUEST_ID: request_id,
        _LABEL_TRACE_ID: trace_id,
        _LABEL_SERVICE_NAME: effective_service,
    }
    for key in (_LABEL_USER_ID, _LABEL_COMPANY_ID, _LABEL_NAMESPACE, _LABEL_SESSION_ID):
        value = log_ctx.get(key)
        if isinstance(value, str) and value.strip():
            labels[key] = value.strip()
    return labels


async def kiq_with_context(
    task: AsyncTaskiqDecoratedTask[..., JsonValue],
    *args: JsonValue,
    override_request_id: str | None = None,
    override_trace_id: str | None = None,
    service_name: str | None = None,
    background_kind: str | None = None,
    extra_labels: dict[str, str] | None = None,
    **kwargs: JsonValue,
) -> AsyncTaskiqTask[JsonValue]:
    """Поставить задачу в очередь, прикрепив обязательные лог-метки."""
    labels = build_log_labels(
        override_request_id=override_request_id,
        override_trace_id=override_trace_id,
        service_name=service_name,
        background_kind=background_kind,
    )
    if extra_labels:
        for key, value in extra_labels.items():
            if not value.strip():
                raise ValueError(
                    f"kiq_with_context: label {key!r} должен быть непустой строкой"
                )
            labels[key] = value.strip()
    return await task.kicker().with_labels(**labels).kiq(*args, **kwargs)


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
    """Вернуть AsyncKicker для task-name contract без импорта worker implementation."""
    if not task_name.strip():
        raise ValueError("kicker_for_task_name_with_log_labels: task_name пустой")
    labels = build_log_labels(
        override_request_id=override_request_id,
        override_trace_id=override_trace_id,
        service_name=service_name,
        background_kind=background_kind,
    )
    if extra_labels:
        for key, value in extra_labels.items():
            if not value.strip():
                raise ValueError(
                    f"kicker_for_task_name_with_log_labels: label {key!r} должен быть непустой строкой"
                )
            labels[key] = value.strip()
    return AsyncKicker(task_name.strip(), broker, labels)


async def kiq_task_name_with_context(
    task_name: str,
    broker: AsyncBroker,
    *args: JsonValue,
    override_request_id: str | None = None,
    override_trace_id: str | None = None,
    service_name: str | None = None,
    background_kind: str | None = None,
    extra_labels: dict[str, str] | None = None,
    **kwargs: JsonValue,
) -> AsyncTaskiqTask[JsonValue]:
    """Поставить TaskIQ задачу по имени, не импортируя модуль-исполнитель."""
    kicker = kicker_for_task_name_with_log_labels(
        task_name,
        broker,
        override_request_id=override_request_id,
        override_trace_id=override_trace_id,
        service_name=service_name,
        background_kind=background_kind,
        extra_labels=extra_labels,
    )
    return await kicker.kiq(*args, **kwargs)


def kicker_with_log_labels(
    task: AsyncTaskiqDecoratedTask[..., JsonValue],
    *,
    override_request_id: str | None = None,
    override_trace_id: str | None = None,
    service_name: str | None = None,
    background_kind: str | None = None,
    extra_labels: dict[str, str] | None = None,
) -> AsyncKicker[..., JsonValue]:
    """
    Вернуть AsyncKicker уже с прикреплёнными log-labels.

    Полезно когда нужен дополнительный with_task_id(...), with_broker(...) и т.д.
    """
    labels = build_log_labels(
        override_request_id=override_request_id,
        override_trace_id=override_trace_id,
        service_name=service_name,
        background_kind=background_kind,
    )
    if extra_labels:
        for key, value in extra_labels.items():
            if not value.strip():
                raise ValueError(
                    f"kicker_with_log_labels: label {key!r} должен быть непустой строкой"
                )
            labels[key] = value.strip()
    return task.kicker().with_labels(**labels)


def _resolve_id(
    override: str | None,
    from_ctx: object,
    *,
    background_kind: str | None,
) -> str:
    if override is not None:
        if not override.strip():
            raise ValueError("override id должен быть непустой строкой или None")
        return override.strip()
    if isinstance(from_ctx, str) and from_ctx.strip():
        return from_ctx.strip()
    if not background_kind or not background_kind.strip():
        raise ValueError(
            "kiq_with_context: вне request-скоупа (нет request_id/trace_id в лог-контексте) обязателен background_kind, например 'background', 'sched', 'cron'."
        )
    prefix = background_kind.strip()
    return f"{prefix}:{uuid.uuid4().hex}"


__all__ = [
    "build_log_labels",
    "kicker_for_task_name_with_log_labels",
    "kicker_with_log_labels",
    "kiq_task_name_with_context",
    "kiq_with_context",
]
