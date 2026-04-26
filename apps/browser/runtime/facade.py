"""
Сборка Browser Runtime для DI и тестов.
"""

from __future__ import annotations

from typing import Optional

from apps.browser.control.contracts import BrowserControlAdapter
from apps.browser.control.observe_store import ControlObserveStore
from apps.browser.runtime.cdp_pool import CDPConnectionPool
from apps.browser.runtime.context_factory import ContextFactory
from apps.browser.runtime.interactor import PlaywrightBrowserInteractor
from apps.browser.runtime.lifecycle import CDPLifecycleManagerImpl
from apps.browser.runtime.page_lease_manager import PageLeaseManager
from apps.browser.runtime.session_store import SessionStateStore
from apps.browser.runtime.types import BrowserRuntimeSettingsView


class BrowserRuntimeFacade:
    """
    Композиционный фасад Browser Runtime.

    Мотивация:
    - Дать единую точку сборки и доступа к runtime-компонентам.
    - Упростить DI и тестирование: контейнеру и API нужен один объект вместо множества.

    Связи:
    - Создаётся DI-контейнером и используется HTTP API.
    - Сшивает transport, контексты, lease, interactor, lifecycle и observe store.

    Состояние:
    - Хранит runtime-компоненты процесса.
    - Лениво создаёт `control_adapter` по настройке `control_backend`.

    Инварианты:
    - Внутренние компоненты инициализируются в согласованной связке.
    - `stop()` закрывает контексты до остановки CDP пула.

    Переиспользование:
    - Стоит: как стандартный entrypoint runtime-а для HTTP API и интеграционных тестов.
    - Не стоит: если нужен частичный runtime в узком юнит-тесте — лучше инстанцировать
      отдельные компоненты напрямую.
    """
    def __init__(self, settings: BrowserRuntimeSettingsView) -> None:
        self.settings = settings
        self.pool = CDPConnectionPool()
        self.context_factory = ContextFactory()
        self.session_store = SessionStateStore()
        self.lease_manager = PageLeaseManager(self.context_factory)
        self.lifecycle = CDPLifecycleManagerImpl(
            self.pool,
            self.lease_manager,
        )
        self.interactor = PlaywrightBrowserInteractor(
            pool=self.pool,
            session_store=self.session_store,
            lease_manager=self.lease_manager,
            settings=settings,
        )
        self.observe_store = ControlObserveStore()
        self._control_adapter: Optional[BrowserControlAdapter] = None

    @property
    def control_adapter(self) -> BrowserControlAdapter:
        if self._control_adapter is None:
            from apps.browser.control.factory import build_browser_control_adapter

            self._control_adapter = build_browser_control_adapter(
                backend=self.settings.control_backend,
                facade=self,
            )
        return self._control_adapter

    async def stop(self) -> None:
        await self.lease_manager.close_all()
        await self.pool.stop()
