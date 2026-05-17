"""
DI контейнер сервиса browser.
"""

from __future__ import annotations

from typing import Optional

from apps.browser.config import get_browser_settings, settings_to_runtime_view
from apps.browser.orchestration.runtime_facade import BrowserRuntimeFacade
from core.container import BaseContainer, lazy
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
    def browser_runtime(self):
        return BrowserRuntimeFacade(settings_to_runtime_view(get_browser_settings()))


_browser_container: Optional[BrowserContainer] = None


def get_browser_container() -> BrowserContainer:
    global _browser_container
    if _browser_container is None:
        settings = get_browser_settings()
        if not settings.database.shared_url:
            raise ValueError("database.shared_url is required для сервиса browser")
        _browser_container = BrowserContainer(
            db_url=settings.database.shared_url,
            shared_db_url=settings.database.shared_url,
        )
        logger.info("BrowserContainer инициализирован")
    return _browser_container


def reset_browser_container() -> None:
    global _browser_container
    _browser_container = None
