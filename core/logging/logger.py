from __future__ import annotations

import structlog


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Единственный способ получить логгер во всех сервисах и в core.

    Возвращает structlog BoundLogger, совместимый с уровнем stdlib (info,
    debug, warning, error, exception, critical). Поддерживает kwargs для
    структурированных полей.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("get_logger требует непустое строковое имя (обычно __name__)")
    return structlog.stdlib.get_logger(name)
