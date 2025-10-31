"""
Dependency Injection Container для управления зависимостями.

Архитектура:
- Container - объект с ленивой инициализацией через __getattr__
- Один Container на event loop (аналогично engine в database.py)
- Контекстов может быть много в одном loop (разные Task), но контейнер один
- Доступ через атрибуты: container.storage, container.agent_factory (синхронный)
- Сервисы инициализируются только при первом обращении
- Отложенные импорты избегают циркулярных зависимостей
- Сохранен тот же синхронный интерфейс доступа
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Optional, Dict

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
    from app.db.repositories import Storage, AgentRepository, FlowRepository, TaskRepository, SessionRepository, ToolRepository
    from app.db.repositories.mcp_repository import MCPServerRepository
    from app.core.agent_factory import AgentFactory
    from app.core.flow_factory import FlowFactory
    from app.core.tool_factory import ToolFactory
    from app.core.graph_builder import GraphBuilder
    from app.core.migration import Migrator
    from app.services.variables_service import VariablesService
    from app.core.core_clients.s3_client import S3ClientFactory
    from app.identity.auth_service import AuthService
    from app.services.billing_service import BillingService
    from app.services.payment_service import PaymentService
    from app.interfaces.factory import InterfaceFactory

logger = logging.getLogger(__name__)

# Глобальный системный контейнер для сервисов, используемых ДО установки request-контекста
_system_container: Optional["Container"] = None

# Словарь для хранения Container для каждого event loop (аналогично _engines в database.py)
_containers: Dict[int, "Container"] = {}


def get_system_container() -> "Container":
    """Получает глобальный системный контейнер"""
    global _system_container
    if _system_container is None:
        raise RuntimeError(
            "Системный контейнер не инициализирован! "
            "Вызовите initialize_system_container() при старте приложения."
        )
    return _system_container


def set_system_container(container: "Container") -> None:
    """Устанавливает глобальный системный контейнер"""
    global _system_container
    _system_container = container


def initialize_system_container() -> "Container":
    """Инициализирует системный контейнер"""
    global _system_container
    if _system_container is None:
        _system_container = Container()
        logger.info("Системный контейнер инициализирован")
    return _system_container


async def get_container_for_loop() -> "Container":
    """
    Лениво создает Container для текущего event loop.

    Аналогично get_session_factory() в database.py.
    Один контейнер на event loop - все контексты в этом loop используют общий контейнер.
    """
    from app.db.database import get_session_factory

    loop = asyncio.get_running_loop()
    loop_id = id(loop)

    # Если контейнер для этого loop'а уже есть, возвращаем его
    if loop_id in _containers:
        return _containers[loop_id]

    # Создаем новый контейнер для этого event loop
    logger.debug(f"🔧 Создаем новый Container для event loop {loop_id}")
    container = Container()

    # Инициализируем session_factory для этого loop
    container._session_factory = await get_session_factory()

    _containers[loop_id] = container
    logger.info(f"✅ Container создан для event loop {loop_id}")

    return container


class Container:
    """Контейнер зависимостей с ленивой инициализацией сервисов"""

    def __init__(self):
        # Базовые зависимости (инициализируются сразу)
        self.engine: Optional["AsyncEngine"] = None
        self._session_factory: Optional["async_sessionmaker"] = None

        # Сервисы с ленивой инициализацией
        self._storage: Optional["Storage"] = None
        self._agent_repository: Optional["AgentRepository"] = None
        self._flow_repository: Optional["FlowRepository"] = None
        self._task_repository: Optional["TaskRepository"] = None
        self._session_repository: Optional["SessionRepository"] = None
        self._tool_repository: Optional["ToolRepository"] = None
        self._mcp_server_repository: Optional["MCPServerRepository"] = None
        self._agent_factory: Optional["AgentFactory"] = None
        self._tool_factory: Optional["ToolFactory"] = None
        self._flow_factory: Optional["FlowFactory"] = None
        self._graph_builder: Optional["GraphBuilder"] = None
        self._variables_service: Optional["VariablesService"] = None
        self._s3_factory: Optional["S3ClientFactory"] = None
        self._auth_service: Optional["AuthService"] = None
        self._billing_service: Optional["BillingService"] = None
        self._payment_service: Optional["PaymentService"] = None
        self._interface_factory: Optional["InterfaceFactory"] = None
        self._migrator: Optional["Migrator"] = None

        # Флаг инициализации базовых зависимостей
        self._initialized = False

    def _ensure_initialized(self):
        """Инициализирует базовые зависимости если еще не инициализированы"""
        if not self._initialized:
            # Не инициализируем session_factory здесь - это будет сделано при первом обращении к storage
            self._initialized = True

    def __getattr__(self, name: str):
        """Ленивая инициализация сервисов при обращении к атрибутам"""

        # Маппинг имен атрибутов на приватные поля
        service_map = {
            'storage': '_storage',
            'agent_repository': '_agent_repository',
            'flow_repository': '_flow_repository',
            'task_repository': '_task_repository',
            'session_repository': '_session_repository',
            'tool_repository': '_tool_repository',
            'mcp_server_repository': '_mcp_server_repository',
            'agent_factory': '_agent_factory',
            'tool_factory': '_tool_factory',
            'flow_factory': '_flow_factory',
            'graph_builder': '_graph_builder',
            'variables_service': '_variables_service',
            's3_factory': '_s3_factory',
            'auth_service': '_auth_service',
            'billing_service': '_billing_service',
            'payment_service': '_payment_service',
            'interface_factory': '_interface_factory',
            'migrator': '_migrator',
        }

        if name not in service_map:
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

        private_name = service_map[name]
        service = getattr(self, private_name)

        if service is None:
            # Инициализируем сервис
            self._ensure_initialized()

            if name == 'storage':
                from app.db.repositories import Storage
                service = Storage()
                # Устанавливаем session_factory из контейнера
                service.session_factory = self._session_factory

            elif name == 'agent_repository':
                from app.db.repositories import AgentRepository
                service = AgentRepository(self.storage)

            elif name == 'flow_repository':
                from app.db.repositories import FlowRepository
                service = FlowRepository(self.storage)

            elif name == 'task_repository':
                from app.db.repositories import TaskRepository
                service = TaskRepository(self.storage)

            elif name == 'session_repository':
                from app.db.repositories import SessionRepository
                service = SessionRepository(self.storage)

            elif name == 'tool_repository':
                from app.db.repositories import ToolRepository
                service = ToolRepository(self.storage)

            elif name == 'mcp_server_repository':
                from app.db.repositories.mcp_repository import MCPServerRepository
                service = MCPServerRepository(self.storage)

            elif name == 'agent_factory':
                from app.core.agent_factory import AgentFactory
                service = AgentFactory(self.agent_repository)

            elif name == 'tool_factory':
                from app.core.tool_factory import ToolFactory
                service = ToolFactory()

            elif name == 'flow_factory':
                from app.core.flow_factory import FlowFactory
                service = FlowFactory(self.flow_repository, self.session_repository, self.storage)

            elif name == 'graph_builder':
                from app.core.graph_builder import GraphBuilder
                service = GraphBuilder()

            elif name == 'variables_service':
                from app.services.variables_service import VariablesService
                service = VariablesService(self.storage)

            elif name == 's3_factory':
                from app.core.core_clients.s3_client import S3ClientFactory
                service = S3ClientFactory()

            elif name == 'auth_service':
                from app.identity.auth_service import AuthService
                service = AuthService(self.storage)

            elif name == 'billing_service':
                from app.services.billing_service import BillingService
                service = BillingService(self.storage)

            elif name == 'payment_service':
                from app.services.payment_service import PaymentService
                service = PaymentService(self.storage)

            elif name == 'interface_factory':
                from app.interfaces.factory import InterfaceFactory
                service = InterfaceFactory(self.storage, self.flow_repository)

            elif name == 'migrator':
                from app.core.migration import Migrator
                service = Migrator()

            # Сохраняем инициализированный сервис
            setattr(self, private_name, service)

        return service

    @property
    def session_factory(self):
        """Ленивая инициализация session_factory"""
        if self._session_factory is None:
            # В ленивой инициализации мы не можем синхронно инициализировать session_factory
            # Полагаемся на то, что он будет инициализирован через AsyncSessionLocal
            # при первом использовании Storage
            raise RuntimeError(
                "Session factory не инициализирован! "
                "Используйте await get_session_factory() для инициализации или "
                "обратитесь к storage через get_container().storage"
            )

        return self._session_factory


def get_container() -> Container:
    """
    Получает контейнер зависимостей для текущего event loop.

    Контейнер привязан к event loop, а не к контексту!
    Один контейнер на loop - все контексты (Task) в этом loop используют общий контейнер.
    Аналогично архитектуре в database.py (engine и session_factory).
    """
    # Проверяем наличие контекста (должен быть установлен для большинства операций)
    from app.core.context import get_context
    context = get_context()
    if context is None:
        logger.error(
            "⚠️ ВНИМАНИЕ: get_container() вызван без установленного контекста! "
            "Это может привести к проблемам с изоляцией данных между компаниями. "
            "Убедитесь, что set_context() был вызван перед использованием контейнера."
        )
        raise RuntimeError(
            "Контекст не установлен! "
            "Используйте set_context() для установки контекста перед использованием контейнера."
        )

    try:
        loop = asyncio.get_running_loop()
        loop_id = id(loop)

        # Если контейнер для этого loop'а уже есть, возвращаем его
        if loop_id in _containers:
            return _containers[loop_id]

        # Если контейнера еще нет - это ошибка (должен быть создан через get_container_for_loop)
        raise RuntimeError(
            f"Container для event loop {loop_id} не инициализирован! "
            f"Используйте await get_container_for_loop() для инициализации."
        )

    except RuntimeError as e:
        if "no running event loop" in str(e):
            raise RuntimeError(
                "get_container() требует запущенный event loop. "
                "Используйте get_system_container() для системных операций или "
                "await get_container_for_loop() для создания контейнера."
            ) from e
        raise
