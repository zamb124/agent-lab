"""
DI контейнер idle worker.

idle_worker исполняет фоновые задачи shared-доменов платформы (AI model catalog,
почта и календарь, платежи и settlement биллинга, push, retention файлов), поэтому ему
достаточно `BaseContainer`: все нужные репозитории и сервисы shared БД уже в нём.
Задачи, которым нужен runtime flows (MCP catalog, tool tag groups, email-триггеры),
живут в `apps/flows/src/tasks/` и исполняются flows_worker.
"""

from __future__ import annotations

from core.config import get_settings
from core.container import BaseContainer, ContainerRegistry
from core.logging import get_logger

logger = get_logger(__name__)


class IdleWorkerContainer(BaseContainer):
    """Контейнер idle worker — shared-домены платформы без flows-БД."""


def _create_idle_worker_container() -> IdleWorkerContainer:
    settings = get_settings()
    if not settings.database.shared_url:
        raise ValueError("database.shared_url is not set")
    return IdleWorkerContainer(
        db_url=settings.database.shared_url,
        shared_db_url=settings.database.shared_url,
    )


_idle_worker_registry: ContainerRegistry[IdleWorkerContainer] = ContainerRegistry(
    _create_idle_worker_container, name="IdleWorkerContainer"
)

get_container = _idle_worker_registry.get
set_container = _idle_worker_registry.set
reset_container = _idle_worker_registry.reset
