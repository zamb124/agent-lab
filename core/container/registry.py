"""
Каноническая обёртка singleton-контейнера сервиса.

Зачем
-----
В каждом `apps/<svc>/container.py` руками писалась одна и та же тройка
`get_<svc>_container() / set_<svc>_container() / reset_<svc>_container()`
поверх module-level `_<svc>_container: <Container> | None = None`.

15 копий одного и того же кода — это:
- 15 потенциально разных трактовок lazy-инициализации,
- 15 копий `logger.info("…Container инициализирован")` без единого формата,
- 15 копий проверок `settings.database.* not None`, разбросанных по апп-коду,
- невозможность ввести что-то новое (например, hook на reset, метрику
  cold-start контейнера) единообразно во всех сервисах.

Один источник правды — `ContainerRegistry`. Сервис описывает только
factory создания своего контейнера; реестр обеспечивает singleton-семантику
с явной типизацией без `Any` / без `cast`.

Контракт использования (apps/<svc>/container.py)
------------------------------------------------

```python
from core.container.registry import ContainerRegistry


def _create_crm_container() -> CRMContainer:
    settings = get_crm_settings()
    if not settings.database.crm_url:
        raise ValueError("database.crm_url не задан")
    return CRMContainer(
        db_url=settings.database.crm_url,
        shared_db_url=settings.database.shared_url,
    )


_crm_registry = ContainerRegistry(_create_crm_container, name="CRMContainer")

get_crm_container = _crm_registry.get
set_crm_container = _crm_registry.set
reset_crm_container = _crm_registry.reset
```

DI-инвариант (main.mdc / architecture.mdc) сохраняется: имена
`get_<svc>_container`, `set_<svc>_container`, `reset_<svc>_container`
остаются такими же на уровне публичного API сервиса и FastAPI
`ContainerDep`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar, final

from core.logging import get_logger

logger = get_logger(__name__)


ContainerT = TypeVar("ContainerT")


@final
class ContainerRegistry(Generic[ContainerT]):
    """
    Singleton-реестр для одного сервисного DI-контейнера.

    Параметризован конкретным типом контейнера — никакого `Any`, никакой
    потери типов при `get/set`. `factory` обязан вернуть полностью
    собранный контейнер либо `raise` (Zero-Guess: реестр не пытается
    сам угадать конфигурацию).
    """

    __slots__ = ("_factory", "_instance", "_name")

    def __init__(self, factory: Callable[[], ContainerT], *, name: str) -> None:
        if not name:
            raise ValueError("ContainerRegistry: name обязателен (используется в логах)")
        self._factory: Callable[[], ContainerT] = factory
        self._name: str = name
        self._instance: ContainerT | None = None

    def get(self) -> ContainerT:
        """Возвращает singleton контейнера, создаёт при первом обращении."""
        if self._instance is None:
            self._instance = self._factory()
            logger.info("container.initialized", container=self._name)
        return self._instance

    def set(self, container: ContainerT) -> None:
        """
        Подменяет инстанс — только для тестов / специальных bootstrap-сценариев.
        Прод-код этим методом не пользуется.
        """
        self._instance = container

    def reset(self) -> None:
        """Сбрасывает инстанс — только для тестов."""
        self._instance = None

    @property
    def is_initialized(self) -> bool:
        return self._instance is not None

    @property
    def name(self) -> str:
        return self._name


__all__ = ["ContainerRegistry"]
