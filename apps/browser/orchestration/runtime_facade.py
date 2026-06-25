"""
Сборка Browser Runtime для DI и тестов.
"""

from __future__ import annotations

from apps.browser.contracts.control import BrowserControlAdapter
from apps.browser.engine.cdp_pool import CDPConnectionPool
from apps.browser.engine.context_factory import ContextFactory
from apps.browser.engine.lifecycle import CDPLifecycleManagerImpl
from apps.browser.engine.page_lease_manager import PageLeaseManager
from apps.browser.engine.playwright_interactor import PlaywrightBrowserInteractor
from apps.browser.engine.session_store import SessionStateStore
from apps.browser.engine.types import BrowserRuntimeSettingsView
from apps.browser.observe.observe_store import ControlObserveStore
from apps.browser.orchestration.control_adapter_factory import build_browser_control_adapter
from core.clients.redis_client import RedisClient
from core.files.service import FilesService
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)


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
    def __init__(
        self,
        settings: BrowserRuntimeSettingsView,
        *,
        redis_client: RedisClient,
        files_service: FilesService,
    ) -> None:
        self.settings: BrowserRuntimeSettingsView = settings
        self.pool: CDPConnectionPool = CDPConnectionPool(
            on_endpoint_disconnected=self._on_endpoint_disconnected,
        )
        self.context_factory: ContextFactory = ContextFactory()
        self.session_store: SessionStateStore = SessionStateStore(
            redis_client=redis_client,
            ttl_sec=settings.session_state_ttl_sec,
        )
        self.lease_manager: PageLeaseManager = PageLeaseManager(
            self.context_factory,
            page_event_logger=self._log_page_event,
            max_contexts=settings.max_contexts,
        )
        self.lifecycle: CDPLifecycleManagerImpl = CDPLifecycleManagerImpl(
            self.pool,
            self.lease_manager,
        )
        self.interactor: PlaywrightBrowserInteractor = PlaywrightBrowserInteractor(
            pool=self.pool,
            session_store=self.session_store,
            lease_manager=self.lease_manager,
            settings=settings,
            files_service=files_service,
        )
        self.observe_store: ControlObserveStore = ControlObserveStore()
        self._control_adapter: BrowserControlAdapter | None = None

    def _log_page_event(self, session_id: str, event: JsonObject) -> None:
        # Debug-события страницы (console/pageerror/network) уходят в Loki сквозным
        # request_id, без локальных файлов и без буфера в памяти.
        logger.info("browser.page_event", session_id=session_id, page_event=event)

    async def _on_endpoint_disconnected(self, endpoint_key: str) -> None:
        """
        CDP endpoint оборвался: закрыть все контексты/lease, привязанные к мёртвому Browser,
        чтобы рантайм не держал записи на закрытый транспорт.
        """
        await self.lease_manager.kill_endpoint(endpoint_key)

    async def reap_once(self) -> None:
        """
        Один проход фоновой очистки: истёкшие lease и idle-контексты.
        """
        await self.lease_manager.sweep_expired(warm_idle_sec=self.settings.warm_idle_sec)
        await self.lease_manager.evict_idle_contexts()
        logger.info(
            "browser.runtime.stats",
            active_contexts=self.lease_manager.total_active_contexts(),
            active_leases=self.lease_manager.total_active_leases(),
            pool_endpoints=self.pool.connected_endpoint_count(),
            max_contexts=self.settings.max_contexts,
        )

    @property
    def control_adapter(self) -> BrowserControlAdapter:
        if self._control_adapter is None:
            self._control_adapter = build_browser_control_adapter(
                backend=self.settings.control_backend,
                facade=self,
            )
        return self._control_adapter

    async def stop(self) -> None:
        await self.lease_manager.close_all()
        await self.pool.stop()
