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

import structlog

from core.logging.context import (
    LogContextScope,
    bind_log_context,
    clear_log_context,
    get_log_context,
    unbind_log_context,
)
from core.logging.contract import (
    LoggingMisconfigured,
    LogRecordPayload,
    REDACT_PLACEHOLDER,
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
from core.logging.setup import reset_logging_for_tests, setup_logging


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Единственный способ получить логгер во всех сервисах и в core.

    Возвращает structlog BoundLogger, совместимый с уровнем stdlib (info,
    debug, warning, error, exception, critical). Поддерживает kwargs для
    структурированных полей::

        logger.info("entity.created", entity_id=eid, kind="note")

    Запрещено в платформе:
    - logging.getLogger(__name__) в apps/** (CI ловит)
    - print(...) в apps/** и core/** (кроме scripts/)
    - logger.info(f"... {value} ...") вместо kwargs
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("get_logger требует непустое строковое имя (обычно __name__)")
    return structlog.stdlib.get_logger(name)


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
    "reset_logging_for_tests",
    "setup_logging",
    "unbind_log_context",
]
