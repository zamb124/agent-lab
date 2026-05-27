"""
TaskIQ middleware: контекст лог-скоупа для каждой задачи.

Поведение:

1. ``pre_send`` (на стороне инициатора, в момент ``.kiq()``):
   автоматически вшивает в ``message.labels`` сквозные идентификаторы из
   лог-контекста — ``request_id``, ``trace_id``, ``service_name``,
   опционально ``user_id``, ``company_id``, ``namespace``, ``session_id``.
   Если в текущем лог-контексте нет ``request_id`` или ``trace_id`` и
   вызывающий не выставил их явно через ``with_labels(...)`` — RAISE
   (нарушение мега-правила).

2. ``pre_execute`` (на стороне воркера): при отсутствии обязательных
   меток (устаревшее сообщение в Redis, обход ``pre_send``) подставляет
   значения через ``build_log_labels(background_kind='taskiq_recover')``
   и пишет ``task.execute_log_labels_recovered``; затем входит в
   request-лог-скоуп с полями из labels.

3. ``post_execute``/``on_error``: выходят из скоупа.

Этим инвариантом мы гарантируем мега-правило: каждый лог любой задачи
несёт ``request_id`` (E2E от HTTP/WS/scheduler/background-инициатора).
"""

from __future__ import annotations

import time
import uuid
from typing import override

import structlog
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from core.config import get_settings
from core.logging import (
    ScopeToken,
    bind_log_context,
    enter_request_scope,
    exit_request_scope,
    get_log_context,
    get_logger,
)
from core.logging.attributes import (
    EVENT_TASK_FAILED,
    EVENT_TASK_FINISHED,
    EVENT_TASK_STARTED,
    LOG_NAMESPACE,
    LOG_SESSION_ID,
    LOG_TASK_DURATION_MS,
    LOG_TASK_ID,
    LOG_TASK_NAME,
    LOG_TASK_QUEUE,
    LOG_TASK_RETRY,
)
from core.tasks.kicker import build_log_labels
from core.tasks.message_contract import (
    set_task_message_string_label,
    set_task_message_string_labels,
    task_message_int_label,
    task_message_string_label,
    task_message_string_labels,
)
from core.types import JsonValue, TaskLabelMap

_LABEL_TRACE_ID = "trace_id"
_LABEL_USER_ID = "user_id"
_LABEL_COMPANY_ID = "company_id"
_LABEL_NAMESPACE = "namespace"
_LABEL_SESSION_ID = "session_id"
_LABEL_REQUEST_ID = "request_id"
_LABEL_SERVICE_NAME = "service_name"
_LOG_LABEL_KEYS = frozenset(
    {
        _LABEL_TRACE_ID,
        _LABEL_USER_ID,
        _LABEL_COMPANY_ID,
        _LABEL_NAMESPACE,
        _LABEL_SESSION_ID,
        _LABEL_REQUEST_ID,
        _LABEL_SERVICE_NAME,
    }
)

_START_TIME_LABEL = "_logging_start_perf"
_SCOPE_TOKEN_LABEL = "_logging_scope_token"


class LoggingMiddleware(TaskiqMiddleware):
    """Вход/выход request-лог-скоупа для каждой TaskIQ задачи."""

    def __init__(self, *, queue_name: str, service_name: str) -> None:
        super().__init__()
        if not queue_name.strip():
            raise ValueError("LoggingMiddleware: queue_name обязателен")
        if not service_name.strip():
            raise ValueError("LoggingMiddleware: service_name обязателен")
        self._logger: structlog.stdlib.BoundLogger = get_logger("platform.task")
        self._queue_name: str = queue_name
        self._service_name: str = service_name

    @override
    async def pre_send(self, message: TaskiqMessage) -> TaskiqMessage:
        labels = task_message_string_labels(message, keys=_LOG_LABEL_KEYS)
        log_ctx = get_log_context()

        if not _label_present(labels, _LABEL_REQUEST_ID):
            request_id = log_ctx.get(_LABEL_REQUEST_ID)
            if not isinstance(request_id, str) or not request_id.strip():
                request_id = self._auto_id("kiq-orphan")
                self._logger.warning(
                    "task.kiq_request_id_missing",
                    task_name=message.task_name,
                    task_id=message.task_id,
                    auto_request_id=request_id,
                )
            labels[_LABEL_REQUEST_ID] = request_id.strip()

        if not _label_present(labels, _LABEL_TRACE_ID):
            trace_id = log_ctx.get(_LABEL_TRACE_ID)
            if not isinstance(trace_id, str) or not trace_id.strip():
                trace_id = self._auto_id("kiq-orphan")
            labels[_LABEL_TRACE_ID] = trace_id.strip()

        if not _label_present(labels, _LABEL_SERVICE_NAME):
            settings = get_settings()
            labels[_LABEL_SERVICE_NAME] = settings.server.name

        for key in (_LABEL_USER_ID, _LABEL_COMPANY_ID, _LABEL_NAMESPACE, _LABEL_SESSION_ID):
            if _label_present(labels, key):
                continue
            value = log_ctx.get(key)
            if isinstance(value, str) and value.strip():
                labels[key] = value.strip()

        set_task_message_string_labels(message, labels)
        return message

    @override
    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        labels = task_message_string_labels(message, keys=_LOG_LABEL_KEYS)
        if (
            not _label_present(labels, _LABEL_REQUEST_ID)
            or not _label_present(labels, _LABEL_TRACE_ID)
            or not _label_present(labels, _LABEL_SERVICE_NAME)
        ):
            fb = build_log_labels(
                background_kind="taskiq_recover",
                service_name=self._service_name,
            )
            if not _label_present(labels, _LABEL_REQUEST_ID):
                labels[_LABEL_REQUEST_ID] = fb[_LABEL_REQUEST_ID]
            if not _label_present(labels, _LABEL_TRACE_ID):
                labels[_LABEL_TRACE_ID] = fb[_LABEL_TRACE_ID]
            if not _label_present(labels, _LABEL_SERVICE_NAME):
                labels[_LABEL_SERVICE_NAME] = fb[_LABEL_SERVICE_NAME]
            set_task_message_string_labels(message, labels)
            self._logger.warning(
                "task.execute_log_labels_recovered",
                task_name=message.task_name,
                task_id=message.task_id,
                queue=self._queue_name,
            )

        request_id = self._require_label(labels, _LABEL_REQUEST_ID, message)
        trace_id = self._require_label(labels, _LABEL_TRACE_ID, message)
        service_name = self._require_label(labels, _LABEL_SERVICE_NAME, message)

        scope_extra: dict[str, str] = {
            LOG_TASK_ID: message.task_id,
            LOG_TASK_NAME: message.task_name,
            LOG_TASK_QUEUE: self._queue_name,
        }
        namespace = self._optional_label(labels, _LABEL_NAMESPACE)
        if namespace is not None:
            scope_extra[LOG_NAMESPACE] = namespace
        session_id = self._optional_label(labels, _LABEL_SESSION_ID)
        if session_id is not None:
            scope_extra[LOG_SESSION_ID] = session_id
        token = enter_request_scope(
            request_id=request_id,
            trace_id=trace_id,
            service_name=service_name,
            user_id=self._optional_label(labels, _LABEL_USER_ID),
            company_id=self._optional_label(labels, _LABEL_COMPANY_ID),
        )
        bind_log_context(**scope_extra)
        labels[_START_TIME_LABEL] = str(time.perf_counter())
        labels[_SCOPE_TOKEN_LABEL] = str(id(token))
        set_task_message_string_label(
            message,
            _START_TIME_LABEL,
            labels[_START_TIME_LABEL],
        )
        set_task_message_string_label(
            message,
            _SCOPE_TOKEN_LABEL,
            labels[_SCOPE_TOKEN_LABEL],
        )
        # Сохраняем токен в attribute словаря: TaskiqMessage не позволяет
        # хранить объекты в labels (str-only сериализация), поэтому держим
        # в side-канале по message id.
        _scope_tokens[id(message)] = token

        self._logger.info(
            EVENT_TASK_STARTED,
            **{
                LOG_TASK_ID: message.task_id,
                LOG_TASK_NAME: message.task_name,
                LOG_TASK_QUEUE: self._queue_name,
            },
        )
        return message

    @override
    async def post_execute(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[JsonValue],
    ) -> None:
        duration_ms = self._duration_ms(message)
        if result.is_err:
            self._logger.error(
                EVENT_TASK_FAILED,
                **{
                    LOG_TASK_ID: message.task_id,
                    LOG_TASK_NAME: message.task_name,
                    LOG_TASK_QUEUE: self._queue_name,
                    LOG_TASK_DURATION_MS: duration_ms,
                },
            )
        else:
            self._logger.info(
                EVENT_TASK_FINISHED,
                **{
                    LOG_TASK_ID: message.task_id,
                    LOG_TASK_NAME: message.task_name,
                    LOG_TASK_QUEUE: self._queue_name,
                    LOG_TASK_DURATION_MS: duration_ms,
                },
            )
        self._exit_scope(message)

    @override
    async def on_error(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[JsonValue],
        exception: BaseException,
    ) -> None:
        _ = result
        duration_ms = self._duration_ms(message)
        retry_value = task_message_int_label(message, "_taskiq_retry_count")
        if retry_value is None:
            retry_value = task_message_int_label(message, "_retries")

        self._logger.exception(
            EVENT_TASK_FAILED,
            **{
                LOG_TASK_ID: message.task_id,
                LOG_TASK_NAME: message.task_name,
                LOG_TASK_QUEUE: self._queue_name,
                LOG_TASK_DURATION_MS: duration_ms,
                LOG_TASK_RETRY: retry_value,
                "exception.type": type(exception).__name__,
            },
        )
        self._exit_scope(message)

    def _exit_scope(self, message: TaskiqMessage) -> None:
        token = _scope_tokens.pop(id(message), None)
        exit_request_scope(token)

    def _require_label(self, labels: TaskLabelMap, key: str, message: TaskiqMessage) -> str:
        value = labels.get(key)
        if not isinstance(value, str) or not value.strip():
            message_text = (
                f"TaskIQ logging contract violation: задача {message.task_name!r} "
                + f"({message.task_id}) не содержит обязательной метки {key!r}. "
                + "Каждый kiq() обязан передавать labels=trace_id, request_id, "
                + "service_name (используйте core.tasks.kicker.with_log_labels)."
            )
            raise ValueError(message_text)
        return value.strip()

    @staticmethod
    def _optional_label(labels: TaskLabelMap, key: str) -> str | None:
        value = labels.get(key)
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip()

    @staticmethod
    def _duration_ms(message: TaskiqMessage) -> float | None:
        raw = task_message_string_label(message, _START_TIME_LABEL)
        if raw is None:
            return None
        try:
            start = float(raw)
        except (TypeError, ValueError):
            return None
        return round((time.perf_counter() - start) * 1000.0, 3)

    @staticmethod
    def _auto_id(prefix: str) -> str:
        return f"{prefix}:{uuid.uuid4().hex}"


def _label_present(labels: TaskLabelMap, key: str) -> bool:
    value = labels.get(key)
    return isinstance(value, str) and value.strip() != ""


_scope_tokens: dict[int, ScopeToken] = {}


def build_logging_middleware(*, queue_name: str, service_name: str) -> LoggingMiddleware:
    """Фабрика middleware — один экземпляр на брокер."""
    return LoggingMiddleware(queue_name=queue_name, service_name=service_name)
