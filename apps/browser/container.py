"""
DI контейнер сервиса browser.
"""

from __future__ import annotations

from apps.browser.config import get_browser_settings, settings_to_runtime_view
from apps.browser.orchestration.runtime_facade import BrowserRuntimeFacade
from core.container import BaseContainer, ContainerRegistry, lazy
from core.logging import get_logger

logger = get_logger(__name__)


class BrowserContainer(BaseContainer):
    """
    DI-контейнер сервиса browser.

    Связи:
    - Создаёт и кэширует `BrowserRuntimeFacade`.
    - Используется HTTP-слоем через `ContainerDep`.

    Состояние:
    - Хранит лениво созданные зависимости контейнера.

    Мотивация:
    - Сконцентрировать сборку runtime в одном месте и исключить дубли в роутерах/сервисах.

    Инварианты:
    - `browser_runtime` собирается только из валидных settings.
    - Инициализация контейнера допускается только при наличии `database.shared_url`.

    Переиспользование:
    - Стоит: как единственный DI entrypoint для HTTP-слоя и тестов сервиса browser.
    """

    @lazy
    def browser_runtime(self) -> BrowserRuntimeFacade:
        return BrowserRuntimeFacade(settings_to_runtime_view(get_browser_settings()))


def _create_browser_container() -> BrowserContainer:
    settings = get_browser_settings()
    if not settings.database.shared_url:
        raise ValueError("database.shared_url is required для сервиса browser")
    return BrowserContainer(
        db_url=settings.database.shared_url,
        shared_db_url=settings.database.shared_url,
    )


_browser_registry: ContainerRegistry[BrowserContainer] = ContainerRegistry(
    _create_browser_container, name="BrowserContainer"
)

get_browser_container = _browser_registry.get
reset_browser_container = _browser_registry.reset
