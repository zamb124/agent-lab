"""
Единый логирующий слой платформы.

Только эти имена допустимы в коде сервисов:

- get_logger(__name__) — единственный способ получить логгер
- setup_logging(service, config) — идемпотентная инициализация процесса
- bind_log_context / unbind_log_context / clear_log_context — управление contextvars
- LogContextScope — контекстный менеджер для временного биндинга

Контракт лог-записи: см. core.logging.contract.LogRecordPayload.
Имена ключей доменных полей: см. core.logging.attributes.
"""

from __future__ import annotations

from core.logging.context import (
    LogContextScope,
    bind_log_context,
    clear_log_context,
    get_log_context,
    unbind_log_context,
)
from core.logging.context import (
    restore_log_context as restore_log_context,
)
from core.logging.contract import (
    REDACT_PLACEHOLDER,
    LoggingMisconfigured,
    LogRecordPayload,
)
from core.logging.scope import (
    LogContractViolation,
    RequestLogScope,
    SystemLogScope,
    enter_request_scope,
    exit_request_scope,
    get_log_scope,
    get_log_scope_requires_user,
)

from .logger import get_logger

__all__ = [
    "LogContextScope",
    "LogContractViolation",
    "LogRecordPayload",
    "LoggingMisconfigured",
    "REDACT_PLACEHOLDER",
    "RequestLogScope",
    "SystemLogScope",
    "bind_log_context",
    "clear_log_context",
    "enter_request_scope",
    "exit_request_scope",
    "get_log_context",
    "get_log_scope",
    "get_log_scope_requires_user",
    "get_logger",
    "restore_log_context",
    "unbind_log_context",
]
