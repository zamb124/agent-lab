"""
Единая точка запуска ASGI-сервисов платформы поверх Granian.

Все `apps/<svc>/main.py` в блоке `if __name__ == "__main__":` зовут
`serve(...)`. В k8s/Docker напрямую используется CLI Granian — этот модуль
нужен только для локальной разработки (`python -m apps.<svc>.main`) и
embedded-сценариев в тестах.

Логирует фактическое состояние Python runtime на старте: free-threaded
билд (cp314t) даёт `gil_enabled=False` и реальный thread-параллелизм
worker'ов; GIL-билд (cp314, локальная macOS-разработка) — `True`.
"""

from __future__ import annotations

import os
import sys

from granian import Granian
from granian.constants import HTTPModes, Interfaces, Loops, RuntimeModes

from core.config import BaseSettings as PlatformBaseSettings
from core.logging import get_logger

logger = get_logger(__name__)

ML_GIL_RESURRECTION_SERVICES = frozenset({"provider_litserve", "rag_worker"})


def _log_python_runtime(service_name: str) -> None:
    is_gil_enabled = bool(sys._is_gil_enabled())  # pyright: ignore[reportPrivateUsage]
    logger.info(
        "service.python_runtime",
        service=service_name,
        python_version=sys.version,
        gil_enabled=is_gil_enabled,
        known_ml_resurrection=service_name in ML_GIL_RESURRECTION_SERVICES,
    )


def serve(service_name: str, target: str, settings: PlatformBaseSettings) -> None:
    _log_python_runtime(service_name)
    # workers=1 для ASGI: каждый worker — отдельный event loop с отдельным ASGI
    # lifespan; пулы asyncpg/sqlalchemy/httpx2/redis локальны к loop и не шарятся
    # между workers. Масштабирование — replicas в k8s.
    workers = settings.server.granian_workers
    runtime_threads = settings.server.granian_runtime_threads
    logger.info(
        "service.granian_topology",
        service=service_name,
        workers=workers,
        runtime_threads=runtime_threads,
        cpu_count=os.cpu_count(),
    )

    server = Granian(
        target=target,
        address=settings.server.host,
        port=settings.server.port,
        interface=Interfaces.ASGI,
        workers=workers,
        runtime_threads=runtime_threads,
        runtime_mode=RuntimeModes.auto,
        loop=Loops.auto,
        http=HTTPModes.auto,
        websockets=True,
        backlog=2048,
        log_enabled=True,
        log_access=False,
        reload=settings.server.debug,
    )
    server.serve()
