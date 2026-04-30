"""
Конфигурация uvicorn-логгеров под единый pipeline платформы.

uvicorn по умолчанию ставит свои handlers (default + access). Мы передаем
этот dict при запуске, чтобы uvicorn не создавал собственных handlers, а
шёл напрямую в root через propagate.

Используется через CLI (--log-config) или внутри embedded uvicorn.run.
В продакшене запуск идёт CLI-командой, поэтому функция get_uvicorn_log_config
сериализуется только для документации; настоящий перехват делает
core.logging.setup_logging() через _silence_noisy_loggers.
"""

from __future__ import annotations

from typing import Any


def get_uvicorn_log_config() -> dict[str, Any]:
    """Минимальный log-config: всё пропагируется в root."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "loggers": {
            "uvicorn": {"level": "INFO", "propagate": True, "handlers": []},
            "uvicorn.error": {"level": "INFO", "propagate": True, "handlers": []},
            "uvicorn.access": {"level": "WARNING", "propagate": True, "handlers": []},
        },
    }
