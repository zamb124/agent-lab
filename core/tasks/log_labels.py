"""Сбор обязательных лог-меток TaskIQ (без зависимости от брокера/реестра).

Выделено из ``kicker`` в отдельный модуль, чтобы разорвать цикл импортов
``broker → logging_middleware → kicker → broker``.
"""

from __future__ import annotations

import uuid

from core.config import get_settings
from core.logging import get_log_context
from core.logging.attributes import LOG_TEST_SCOPE
from core.types import JsonValue

LABEL_REQUEST_ID = "request_id"
LABEL_TRACE_ID = "trace_id"
LABEL_SERVICE_NAME = "service_name"
LABEL_USER_ID = "user_id"
LABEL_COMPANY_ID = "company_id"
LABEL_NAMESPACE = "namespace"
LABEL_SESSION_ID = "session_id"
LABEL_QUEUE_NAME = "queue_name"
LABEL_PRIORITY = "priority"
LABEL_TEST_SCOPE = LOG_TEST_SCOPE


def build_log_labels(
    *,
    override_request_id: str | None = None,
    override_trace_id: str | None = None,
    service_name: str | None = None,
    background_kind: str | None = None,
) -> dict[str, str]:
    """Собрать labels для kiq(): тащит request_id/trace_id/user_id из лог-контекста.

    Если контекст пуст и явных override нет — генерируется фоновый identifier
    с префиксом из ``background_kind`` (например ``cron``, ``sched``,
    ``startup``). Это допустимо только для системных triggerов; HTTP/WS
    handlers всегда работают внутри request scope, где request_id уже есть.

    Исключения:
        ValueError: если override_request_id/override_trace_id явно пустые
            строки (а не None).
    """
    log_ctx = get_log_context()
    settings = get_settings()
    effective_service = (service_name or settings.server.name).strip()
    if not effective_service:
        raise ValueError('build_log_labels: service_name is not set')

    request_id = _resolve_id(
        override_request_id,
        log_ctx.get(LABEL_REQUEST_ID),
        background_kind=background_kind,
    )
    trace_id = _resolve_id(
        override_trace_id,
        log_ctx.get(LABEL_TRACE_ID),
        background_kind=background_kind,
    )

    labels: dict[str, str] = {
        LABEL_REQUEST_ID: request_id,
        LABEL_TRACE_ID: trace_id,
        LABEL_SERVICE_NAME: effective_service,
    }
    for key in (
        LABEL_USER_ID,
        LABEL_COMPANY_ID,
        LABEL_NAMESPACE,
        LABEL_SESSION_ID,
        LABEL_TEST_SCOPE,
    ):
        value = log_ctx.get(key)
        if isinstance(value, str) and value.strip():
            labels[key] = value.strip()
    return labels


def merge_extra_labels(labels: dict[str, str], extra_labels: dict[str, str] | None) -> None:
    if not extra_labels:
        return
    for key, value in extra_labels.items():
        if not value.strip():
            raise ValueError(f"enqueue: label {key!r} must be a non-empty string")
        labels[key] = value.strip()


def _resolve_id(
    override: str | None,
    from_ctx: JsonValue,
    *,
    background_kind: str | None,
) -> str:
    if override is not None:
        if not override.strip():
            raise ValueError('override id must be a non-empty string or None')
        return override.strip()
    if isinstance(from_ctx, str) and from_ctx.strip():
        return from_ctx.strip()
    if not background_kind or not background_kind.strip():
        raise ValueError(
            "enqueue: outside request scope background_kind is required ('background'/'sched'/'cron')"
        )
    return f"{background_kind.strip()}:{uuid.uuid4().hex}"


__all__ = [
    "LABEL_COMPANY_ID",
    "LABEL_NAMESPACE",
    "LABEL_PRIORITY",
    "LABEL_QUEUE_NAME",
    "LABEL_REQUEST_ID",
    "LABEL_SERVICE_NAME",
    "LABEL_SESSION_ID",
    "LABEL_TRACE_ID",
    "build_log_labels",
    "merge_extra_labels",
]
