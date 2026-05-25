"""
DI контейнер idle worker.

Архитектурное решение
---------------------
idle_worker исполняет фоновые задачи, которые принадлежат сразу нескольким
доменам платформы:

- LLM models sync — flow-specific (`LLMModelRepository` живёт в БД flows).
- Calendar / integrations sync — shared (`core/` репозитории).
- Payment sync, span billing settlement — shared (`core/payments`, `core/billing`).
- Push notifications — shared (`core/push`).

Поэтому idle_worker задокументирован как **extension of flows**:
он наследует `FlowContainer` (и через него весь `BaseContainer`),
а не пересобирает зависимости. Это сознательное компромиссное решение
вместо создания parallel-контейнера с дублирующимися `@lazy`-свойствами.

Любые новые задачи idle_worker, которым нужно state из flows-БД, добавляются
в `FlowContainer`. Задачи, которым flows-state не нужен (чисто `core/`),
тоже идут сюда и получают доступ через унаследованные `@lazy` свойства
`BaseContainer`. Это поддерживает Single Source of Truth для DI — нет
дублирования `redis_client`/`storage`/`company_repository` в двух контейнерах.

Worker lifecycle
----------------
- `apps/idle_worker/worker.py` создаёт singleton через `get_container()`.
- `container.use_worker = False` отключает kiq-отправку в очередь
  (задачи внутри idle_worker исполняются in-process).
"""

from __future__ import annotations

from apps.flows.config import get_settings
from apps.flows.src.container import FlowContainer
from core.container import ContainerRegistry
from core.logging import get_logger

logger = get_logger(__name__)


class IdleWorkerContainer(FlowContainer):
    """
    Контейнер idle worker — extension of flows.

    Расширяет `FlowContainer` без новых `@lazy`-свойств: все зависимости
    наследуются. При необходимости задачи idle_worker могут переопределить
    отдельные провайдеры (например, отключить kiq для in-process выполнения).
    """


def _create_idle_worker_container() -> IdleWorkerContainer:
    settings = get_settings()
    container = IdleWorkerContainer(
        db_url=settings.database.flows_url,
        shared_db_url=settings.database.shared_url,
    )
    container.use_worker = False
    return container


_idle_worker_registry: ContainerRegistry[IdleWorkerContainer] = ContainerRegistry(
    _create_idle_worker_container, name="IdleWorkerContainer"
)

get_container = _idle_worker_registry.get
set_container = _idle_worker_registry.set
reset_container = _idle_worker_registry.reset
