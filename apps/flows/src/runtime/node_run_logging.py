"""
Утилиты логирования запусков нод flow runtime.

Пишет компактные события node_start/node_finish/node_error в отдельный файл,
чтобы разбор исполнения графа не тонул в общем логе.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from typing import Any

from core.config import get_settings
from core.logging.formatters import JSONFormatter

_LOGGER_NAME = "flows.node_runs"
_installed = False


def get_node_run_logger() -> logging.Logger:
    """
    Возвращает logger для событий запусков нод.

    Logger настроен на запись в отдельный файл и не всплывает в root handlers.
    """
    global _installed

    logger = logging.getLogger(_LOGGER_NAME)
    if _installed:
        return logger

    settings = get_settings()
    cfg = settings.logging

    log_file = Path("logs/flows_node_runs.log")
    log_file.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=cfg.file_max_bytes,
        backupCount=cfg.file_backup_count,
        encoding="utf-8",
    )
    handler.setLevel(getattr(logging, cfg.level.upper()))
    handler.setFormatter(JSONFormatter())

    logger.handlers.clear()
    logger.setLevel(getattr(logging, cfg.level.upper()))
    logger.addHandler(handler)
    logger.propagate = False

    _installed = True
    return logger


def log_node_event(
    *,
    event: str,
    node_id: str,
    node_type: str,
    duration_ms: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    logger = get_node_run_logger()
    payload: dict[str, Any] = {
        "event": event,
        "node_id": node_id,
        "node_type": node_type,
    }
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if details:
        payload["details"] = details
    logger.info(str(payload))

