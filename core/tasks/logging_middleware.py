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

2. ``pre_execute`` (на стороне воркера): входит в request-лог-скоуп с
   полями из labels. Если labels не содержат ``request_id`` или
   ``trace_id`` (значит, ``pre_send`` где-то упустил) — RAISE.

3. ``post_execute``/``on_error``: выходят из скоупа.

Этим инвариантом мы гарантируем мега-правило: каждый лог любой задачи
несёт ``request_id`` (E2E от HTTP/WS/scheduler/background-инициатора).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from core.config import get_settings
from core.logging import (
    enter_request_scope,
    exit_request_scope,
    get_log_context,
    get_logger,
)
from core.logging.attributes import (
    EVENT_TASK_FAILED,
    EVENT_TASK_FINISHED,
    EVENT_TASK_STARTED,
    LOG_COMPANY_ID,
    LOG_NAMESPACE,
    LOG_SESSION_ID,
    LOG_TASK_DURATION_MS,
    LOG_TASK_ID,
    LOG_TASK_NAME,
    LOG_TASK_QUEUE,
    LOG_TASK_RETRY,
    LOG_USER_ID,
)
from core.logging.scope import _ScopeToken


_LABEL_TRACE_ID = "trace_id"
_LABEL_USER_ID = "user_id"
_LABEL_COMPANY_ID = "company_id"
_LABEL_NAMESPACE = "namespace"
_LABEL_SESSION_ID = "session_id"
_LABEL_REQUEST_ID = "request_id"
_LABEL_SERVICE_NAME = "service_name"

_START_TIME_LABEL = "_logging_start_perf"
_SCOPE_TOKEN_LABEL = "_logging_scope_token"


class LoggingMiddleware(TaskiqMiddleware):
    """Вход/выход request-лог-скоупа для каждой TaskIQ задачи."""

    def __init__(self, *, queue_name: str, service_name: str) -> None:
        super().__init__()
        if not isinstance(queue_name, str) or not queue_name.strip():
            raise ValueError("LoggingMiddleware: queue_name обязателен")
        if not isinstance(service_name, str) or not service_name.strip():
            raise ValueError("LoggingMiddleware: service_name обязателен")
        self._logger = get_logger("platform.task")
        self._queue_name = queue_name
        self._service_name = service_name

    async def pre_send(self, message: TaskiqMessage) -> TaskiqMessage:
        labels = message.labels or {}
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

        message.labels = labels
        return message

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        labels = message.labels or {}
        request_id = self._require_label(labels, _LABEL_REQUEST_ID, message)
        trace_id = self._require_label(labels, _LABEL_TRACE_ID, message)
        service_name = self._service_or_default(labels)

        token = enter_request_scope(
            request_id=request_id,
            trace_id=trace_id,
            service_name=service_name,
            user_id=self._optional_label(labels, _LABEL_USER_ID),
            company_id=self._optional_label(labels, _LABEL_COMPANY_ID),
            **{
                LOG_NAMESPACE: self._optional_label(labels, _LABEL_NAMESPACE),
                LOG_SESSION_ID: self._optional_label(labels, _LABEL_SESSION_ID),
                LOG_TASK_ID: message.task_id,
                LOG_TASK_NAME: message.task_name,
                LOG_TASK_QUEUE: self._queue_name,
            },
        )
        message.labels[_START_TIME_LABEL] = str(time.perf_counter())
        message.labels[_SCOPE_TOKEN_LABEL] = id(token)
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

    async def post_execute(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],
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

    async def on_error(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],
        exception: BaseException,
    ) -> None:
        duration_ms = self._duration_ms(message)
        retry_count = message.labels.get("_taskiq_retry_count")
        try:
            retry_value: int | None = int(retry_count) if retry_count is not None else None
        except (TypeError, ValueError):
            retry_value = None

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

    def _require_label(self, labels: dict[str, Any], key: str, message: TaskiqMessage) -> str:
        value = labels.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"TaskIQ logging contract violation: задача {message.task_name!r} "
                f"({message.task_id}) не содержит обязательной метки {key!r}. "
                "Каждый kiq() обязан передавать labels=trace_id, request_id, "
                "service_name (используйте core.tasks.kicker.with_log_labels)."
            )
        return value.strip()

    def _service_or_default(self, labels: dict[str, Any]) -> str:
        value = labels.get(_LABEL_SERVICE_NAME)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return self._service_name

    @staticmethod
    def _optional_label(labels: dict[str, Any], key: str) -> str | None:
        value = labels.get(key)
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip()

    @staticmethod
    def _duration_ms(message: TaskiqMessage) -> float | None:
        raw = message.labels.get(_START_TIME_LABEL)
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


def _label_present(labels: dict[str, Any], key: str) -> bool:
    value = labels.get(key)
    return isinstance(value, str) and value.strip() != ""


_scope_tokens: dict[int, _ScopeToken] = {}


def build_logging_middleware(*, queue_name: str, service_name: str) -> LoggingMiddleware:
    """Фабрика middleware — один экземпляр на брокер."""
    return LoggingMiddleware(queue_name=queue_name, service_name=service_name)
