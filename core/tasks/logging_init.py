"""
Ранняя инициализация логирования для TaskIQ worker-процессов.

Вызывать синхронно из apps/*_worker/worker.py после загрузки настроек
и до импорта broker, чтобы записи при импорте модулей и внутренние
логи TaskIQ до WORKER_STARTUP шли через единый ProcessorFormatter.
"""

from __future__ import annotations

from typing import Optional

from core.config.models import LoggingConfig
from core.logging import setup_logging


def setup_worker_logging_early(
    service_name: str,
    *,
    logging_config: Optional[LoggingConfig] = None,
) -> None:
    if not isinstance(service_name, str) or not service_name.strip():
        raise ValueError("setup_worker_logging_early: service_name must be a non-empty string")
    setup_logging(
        service_name=service_name.strip(),
        logging_config=logging_config,
    )


__all__ = ["setup_worker_logging_early"]
