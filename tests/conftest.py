"""
Единая конфигурация фикстур для pytest.
Все тесты используют фикстуры отсюда для унификации.
"""
import asyncio
import pytest
import pytest_asyncio
import os
import uuid
import threading
import logging
from pathlib import Path
from typing import Callable, Dict, Optional
from unittest.mock import MagicMock
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ВАЖНО: Переменные окружения ДОЛЖНЫ быть установлены ДО импорта модулей!
# Иначе core/config/base.py создаст settings с неправильными URL
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)

# Две БД как на продакшне
os.environ.setdefault("DATABASE__URL", "postgresql+asyncpg://agent_user:agent_password@localhost:5432/agents_db")
os.environ.setdefault("DATABASE__SHARED_URL", "postgresql+asyncpg://agent_user:agent_password@localhost:5432/shared_db")
os.environ.setdefault("SERVER__DEBUG", "true")
os.environ.setdefault("LLM__DEFAULT_MODEL", "mock-gpt-4")
os.environ.setdefault("LLM__OPENROUTER__ENABLED", "true")
os.environ.setdefault("LLM__OPENROUTER__API_KEY", "test-openrouter-key")
os.environ.setdefault("AUTH__JWT_SECRET_KEY", "test-jwt-secret-key-for-tests-only")
os.environ.setdefault("S3__ENABLED", "true")
os.environ.setdefault("S3__DEFAULT_BUCKET", "vkbucket")

# Теперь можно импортировать модули
from core.db import Storage
from core.context import set_context, clear_context, get_context
from core.models import User, Company, Context
from core.clients import get_llm

from apps.agents.container import get_agents_container
from apps.agents.models import (
    AgentConfig, AgentType, CodeMode, FlowConfig,
    ToolReference, LLMConfig
)

_migration_lock = threading.Lock()
_migration_completed = False

# get_llm() автоматически определяет тестовое окружение через PYTEST_CURRENT_TEST
# (устанавливается pytest автоматически)


@pytest.fixture(scope="session")
def event_loop_policy():
    """Возвращает политику event loop для сессии"""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
def event_loop(event_loop_policy):
    """Общий event loop для всей сессии тестов.
    
    Необходимо для корректной работы PostgreSQL broker в TaskIQ -
    все соединения asyncpg должны быть в одном event loop.
    """
    loop = event_loop_policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()



@pytest.fixture(scope="session", autouse=True)
def setup_mock_llm_configs():
    """Настройка mock LLM для всех агентов (один раз на всю сессию)"""
    from apps.agents.models import LLMConfig

    mock_llm_config = LLMConfig(
        model="mock-gpt-4", 
        temperature=0.3,
        context_window=100000
    )

    import apps.agents.agents.weather.agent as weather_module
    weather_module.WeatherAgent.llm_config = mock_llm_config
    weather_module.TravelInfoAgent.llm_config = mock_llm_config

    import apps.agents.agents.calculator.agent as calc_module
    calc_module.CalculatorAgent.llm_config = mock_llm_config

    import apps.agents.agents.explainer.agent as explainer_module
    explainer_module.ExplainerAgent.llm_config = mock_llm_config

    return mock_llm_config


def _create_e2e_browser_test_user_sync():
    """Создает тестового пользователя для browser e2e тестов через прямой SQL"""
    import subprocess
    import json
    from datetime import datetime, timezone, timedelta
    
    E2E_USER_ID = "e2e_browser_test_user"
    E2E_COMPANY_ID = "e2e_browser_test_company"
    E2E_SUBDOMAIN = "e2ebrowser"
    E2E_SESSION_ID = "e2e_browser_test_session"
    
    now = datetime.now(timezone.utc).isoformat()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    
    user_data = json.dumps({
        "user_id": E2E_USER_ID,
        "provider": "test",
        "provider_user_id": "e2e_browser_test",
        "name": "E2E Browser Test User",
        "status": "active",
        "groups": ["admin"],
        "companies": {E2E_COMPANY_ID: ["admin"]},
        "active_company_id": E2E_COMPANY_ID
    })
    
    company_data = json.dumps({
        "company_id": E2E_COMPANY_ID,
        "subdomain": E2E_SUBDOMAIN,
        "name": "E2E Browser Test Company",
        "tariff_plan": "enterprise",
        "balance": 100000.0,
        "monthly_budget": 50000.0,
        "current_month_spent": 0.0,
        "status": "active"
    })
    
    subdomain_data = json.dumps({
        "subdomain": E2E_SUBDOMAIN,
        "company_id": E2E_COMPANY_ID
    })
    
    # AuthSession для WebSocket авторизации
    auth_session_data = json.dumps({
        "session_id": E2E_SESSION_ID,
        "user_id": E2E_USER_ID,
        "provider": "yandex",
        "created_at": now,
        "expires_at": expires_at,
        "last_activity": now,
        "metadata": {"company_id": E2E_COMPANY_ID}
    })
    
    sql = f"""
    INSERT INTO users (key, value) VALUES ('user:{E2E_USER_ID}', '{user_data}')
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
    
    INSERT INTO storage (key, value) VALUES ('company:{E2E_COMPANY_ID}', '{company_data}')
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
    
    INSERT INTO storage (key, value) VALUES ('subdomain:{E2E_SUBDOMAIN}', '{subdomain_data}')
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
    
    INSERT INTO users (key, value) VALUES ('auth_session:{E2E_SESSION_ID}', '{auth_session_data}')
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
    """
    
    try:
        result = subprocess.run(
            ["psql", "-h", "localhost", "-U", "agent_user", "-d", "shared_db", "-c", sql],
            env={**os.environ, "PGPASSWORD": "agent_password"},
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            logger.info(f"✅ E2E browser test user created: {E2E_USER_ID}")
        else:
            logger.warning(f"⚠️ Failed to create E2E user: {result.stderr}")
    except Exception as e:
        logger.warning(f"⚠️ Could not create E2E user via psql: {e}")


@pytest_asyncio.fixture(scope="session")
async def migrated_db():
    """Миграция БД один раз для всей сессии воркера

    Каждый pytest-xdist воркер имеет свой engine/session_factory/контейнер,
    поэтому session scope безопасен - всё изолировано по воркерам.
    """
    global _migration_completed
    
    if _migration_completed:
        yield
        return
    
    with _migration_lock:
        if _migration_completed:
            yield
            return
        
        # Инициализируем контейнер агентов для тестов
        from core.config import get_settings
        from core.files import initialize_default_processors
        
        settings = get_settings()
        
        container = get_agents_container()
        logger.info("✅ AgentsContainer инициализирован для тестов")
        
        # Инициализируем файловые процессоры
        initialize_default_processors(
            file_repository=container.file_repository,
            storage=container.storage
        )
        logger.info("✅ Файловые процессоры инициализированы для тестов")

        # Создаем контекст миграции
        migration_context = Context(
            user=User(
                user_id="migration_user",
                provider="system",
                provider_user_id="sys_001",
                email="migration@system.local",
                name="Migration User",
                status="active",
                groups=["admin"],
                companies={"system": ["admin"]},
                active_company_id="system"
            ),
            session_id="migration_session",
            platform="system",
            metadata={}
        )

        set_context(migration_context)

        # Создаем таблицы и мигрируем
        from core.db.database import create_tables, get_session_factory
        from core.db.models import Stores, AgentStates  # Явный импорт для регистрации в Base.metadata
        from sqlalchemy import text
        # Service БД (agents_db): storage, tasks, stores, agent_states, otel_spans
        await create_tables(
            db_url=settings.database.url,
            table_names=["storage", "tasks", "stores", "agent_states", "otel_spans"]
        )
        # Проверяем, что таблицы действительно созданы
        session_factory = await get_session_factory(settings.database.url)
        async with session_factory() as session:
            result = await session.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('stores', 'agent_states')")
            )
            created_tables = [row[0] for row in result]
            if 'stores' not in created_tables or 'agent_states' not in created_tables:
                logger.error(f"⚠️  Таблицы не созданы! Ожидались: stores, agent_states. Созданы: {created_tables}")
                raise RuntimeError(f"Таблицы stores и agent_states не созданы в БД {settings.database.url}")
            logger.info(f"✅ Таблицы проверены: {created_tables}")
        # Shared БД (shared_db): users, storage, variables
        if settings.database.shared_url:
            await create_tables(
                db_url=settings.database.shared_url,
                table_names=["users", "storage", "variables"]
            )

        migrator = get_agents_container().migrator
        await migrator.run_full_migration()
        logger.info("✅ Миграция БД выполнена для воркера")
        
        # Создаем тестового пользователя для browser e2e тестов (синхронно через psql)
        _create_e2e_browser_test_user_sync()
        
        _migration_completed = True

    yield

    # Cleanup: закрываем соединения с БД для текущего event loop
    # Важно: закрываем только для текущего loop, так как каждый тест может иметь свой loop
    from core.db.database import close_db
    try:
        await close_db()
    except Exception as e:
        logger.debug(f"Ошибка при закрытии БД соединений (может быть нормально): {e}")
    
    # Очищаем контекст
    clear_context()
    
    # Принудительная сборка мусора для освобождения памяти
    import gc
    gc.collect()


@pytest_asyncio.fixture
async def storage(migrated_db):
    """Storage из контейнера воркера"""

    return get_agents_container().storage


@pytest_asyncio.fixture
async def agent_factory(migrated_db):
    """AgentFactory из контейнера воркера"""
    return get_agents_container().agent_factory


@pytest_asyncio.fixture
async def agent_repo(migrated_db):
    """AgentRepository из контейнера воркера"""
    return get_agents_container().agent_repository


@pytest_asyncio.fixture
async def flow_repo(migrated_db):
    """FlowRepository из контейнера воркера"""
    return get_agents_container().flow_repository


@pytest_asyncio.fixture
async def task_repo(migrated_db):
    """TaskRepository из контейнера воркера"""
    return get_agents_container().task_repository


@pytest_asyncio.fixture
async def session_repo(migrated_db):
    """SessionRepository из контейнера воркера"""
    return get_agents_container().session_repository


@pytest_asyncio.fixture
async def tool_repo(migrated_db):
    """ToolRepository из контейнера воркера"""
    return get_agents_container().tool_repository


@pytest_asyncio.fixture
async def mcp_repo(migrated_db):
    """MCPServerRepository из контейнера воркера"""
    return get_agents_container().mcp_server_repository


@pytest_asyncio.fixture
async def company_repo(migrated_db):
    """CompanyRepository из контейнера воркера"""
    return get_agents_container().company_repository


@pytest_asyncio.fixture
async def user_repo(migrated_db):
    """UserRepository из контейнера воркера"""
    return get_agents_container().user_repository


@pytest_asyncio.fixture
async def subdomain_repo(migrated_db):
    """SubdomainRepository из контейнера воркера"""
    return get_agents_container().subdomain_repository


@pytest_asyncio.fixture
async def variable_repo(migrated_db):
    """VariableRepository из контейнера воркера"""
    return get_agents_container().variable_repository


@pytest_asyncio.fixture
async def usage_repo(migrated_db):
    """UsageRepository из контейнера воркера"""
    return get_agents_container().usage_repository


@pytest_asyncio.fixture
async def file_repo(migrated_db):
    """FileRepository из контейнера воркера"""
    return get_agents_container().file_repository


@pytest_asyncio.fixture
async def flow_factory(migrated_db):
    """FlowFactory из контейнера воркера"""
    return get_agents_container().flow_factory


@pytest_asyncio.fixture
async def tool_factory(migrated_db):
    """ToolFactory из контейнера воркера"""
    return get_agents_container().tool_factory


@pytest_asyncio.fixture
async def system_context(migrated_db):
    """Системный контекст для чтения системных сущностей (flows, agents)"""
    from core.models import Company, User
    from core.models.context_models import Context

    system_context = Context(
        user=User(
            user_id="migration_user",
            provider="system",
            provider_user_id="sys_001",
            email="migration@system.local",
            name="Migration User",
            status="active",
            groups=["admin"],
            companies={"system": ["admin"]},
            active_company_id="system"
        ),
        session_id="migration_session",
        platform="system",
        active_company=Company(
            company_id="system",
            subdomain="system",
            name="System Company",
            status="active"
        )
    )
    set_context(system_context)
    return system_context


@pytest_asyncio.fixture
async def migrator(migrated_db):
    """Migrator для каждого теста"""
    return get_agents_container().migrator


@pytest_asyncio.fixture
async def test_company() -> Company:
    """Тестовая компания с достаточным балансом и уникальным ID"""
    from core.models.billing_models import TariffPlan
    import uuid
    
    unique_suffix = uuid.uuid4().hex[:8]
    return Company(
        company_id=f"test_company_{unique_suffix}",
        subdomain=f"test_{unique_suffix}",
        name="Test Company",
        tariff_plan=TariffPlan.ENTERPRISE,
        balance=100000.0,
        monthly_budget=50000.0,
        current_month_spent=0.0,
        status="active"
    )


@pytest_asyncio.fixture
async def test_user(test_company: Company) -> User:
    """Тестовый пользователь с уникальным ID для изоляции тестов"""
    unique_suffix = uuid.uuid4().hex[:8]
    return User(
        user_id=f"test_user_{unique_suffix}",
        provider="yandex",
        provider_user_id=f"test_{unique_suffix}",
        email=f"test_{unique_suffix}@example.com",
        name="Test User",
        status="active",
        groups=["user"],
        companies={test_company.company_id: ["admin"]},
        active_company_id=test_company.company_id
    )


@pytest_asyncio.fixture
async def test_context(test_user: User, test_company: Company, migrated_db, company_repo):
    """Тестовый контекст для тестов (используется явно где нужен полный контекст)

    Добавляй в параметры теста если нужен контекст с пользователем и компанией.
    Каждый тест получает уникальный session_id для изоляции.
    
    Сохраняет test_company в БД для межсервисного взаимодействия.
    """
    # Сохраняем компанию в БД для доступа из других процессов (agents_service)
    await company_repo.set(test_company)
    
    unique_session_id = f"test_session_{uuid.uuid4().hex[:8]}"
    context = Context(
        user=test_user,
        session_id=unique_session_id,
        platform="api",
        active_company=test_company,
        user_companies=[test_company],
        metadata={}
    )

    set_context(context)
    yield context

    clear_context()
    # Очистка компании после теста
    await company_repo.delete(test_company.company_id)


@pytest_asyncio.fixture(scope="function", autouse=True)
async def cleanup_after_test():
    """Автоматическая очистка после каждого теста для предотвращения утечек памяти"""
    yield
    
    # Очищаем контекст после каждого теста
    clear_context()
    
    
    # Принудительная сборка мусора для освобождения памяти
    import gc
    # Собираем несколько раз для более агрессивной очистки
    for _ in range(3):
        collected = gc.collect()
        if collected == 0:
            break



@pytest_asyncio.fixture
async def save_test_company(test_company: Company):
    """Сохраняет тестовую компанию в БД"""
    container = get_agents_container()
    company_repo = container.company_repository
    subdomain_repo = container.subdomain_repository
    
    await company_repo.set(test_company)
    
    from core.db.repositories.subdomain_repository import SubdomainMapping
    subdomain_mapping = SubdomainMapping(
        subdomain=test_company.subdomain,
        company_id=test_company.company_id
    )
    await subdomain_repo.set(subdomain_mapping)

    yield test_company

    try:
        await company_repo.delete(test_company.company_id)
        await subdomain_repo.delete(test_company.subdomain)
    except:
        pass


@pytest_asyncio.fixture
async def setup_mcp_servers(mcp_repo, test_company: Company):
    """
    Создает тестовые MCP серверы для интеграционных тестов.

    Создает Context7 MCP сервер с тестовым API ключом.
    """
    from apps.agents.models.mcp_models import MCPServerConfig, MCPTransportType
    import os

    servers = []

    # Context7 - используем предоставленный API ключ
    context7_api_key = os.getenv("CONTEXT7_API_KEY", "ctx7sk-00fdd198-322d-4fe7-b63d-43a479dd5ff0")

    context7 = MCPServerConfig(
        server_id="context7",
        company_id=test_company.company_id,
        name="Context7 Documentation",
        description="AI-powered documentation search",
        url="https://mcp.context7.com/mcp",
        transport_type=MCPTransportType.HTTP,
        headers={"Authorization": f"Bearer {context7_api_key}"},
        is_active=True,
        auto_sync_tools=False
    )
    await mcp_repo.set(context7)
    servers.append(context7)

    yield servers

    # Очистка
    for server in servers:
        await mcp_repo.delete(server.server_id)


@pytest_asyncio.fixture
async def variables_service(migrated_db):
    """VariablesService для работы с переменными компании

    Контекст будет доступен через get_context() благодаря test_context с autouse=True
    Зависит от migrated_db для инициализации БД в правильном event loop
    """
    from apps.agents.container import get_agents_container
    container = get_agents_container()
    return container.variables_service


@pytest_asyncio.fixture
async def unique_id():
    """Генератор уникальных ID для тестов"""
    def _generate(prefix: str = "test") -> str:
        return f"{prefix}_{uuid.uuid4().hex[:8]}"
    return _generate


@pytest_asyncio.fixture
async def mock_llm():
    """Настроенный MockLLM для теста"""
    llm = get_llm("mock-gpt-4")
    llm.reset_call_counts()
    return llm


@pytest_asyncio.fixture
async def httpx_client():
    """HTTP клиент для тестирования API"""
    import httpx
    async with httpx.AsyncClient(base_url="http://localhost:8001") as client:
        yield client


@pytest_asyncio.fixture(scope="session")
async def agents_app(migrated_db):
    """FastAPI приложение для agents сервиса (порт 8001)"""
    from apps.agents.main import create_app
    return create_app()


@pytest_asyncio.fixture(scope="session")
async def frontend_app(migrated_db):
    """FastAPI приложение для frontend сервиса (порт 8002)"""
    from apps.frontend.main import create_app
    from apps.frontend.core.plugin_loader import discover_and_load_plugins
    
    app = create_app()
    
    # Загружаем плагины вручную т.к. lifespan не выполняется при ASGITransport
    await discover_and_load_plugins(app)
    
    return app


@pytest_asyncio.fixture
async def frontend_client(frontend_app, test_context, test_user, test_company):
    """
    HTTP клиент для тестирования frontend API с авторизацией.
    
    Создает JWT токен и передает его в cookies для авторизации.
    Использует реальное FastAPI приложение через ASGITransport.
    Host заголовок с поддоменом для определения компании.
    """
    import httpx
    from httpx import ASGITransport
    from core.utils.tokens import get_token_service
    from core.db.repositories.subdomain_repository import SubdomainMapping
    
    container = frontend_app.state.container
    
    # Сохраняем компанию и subdomain
    await container.company_repository.set(test_company)
    
    subdomain_mapping = SubdomainMapping(
        subdomain=test_company.subdomain,
        company_id=test_company.company_id
    )
    await container.subdomain_repository.set(subdomain_mapping)
    
    # Сохраняем пользователя
    await container.user_repository.set(test_user)
    
    # Создаем JWT токен
    unique_session_id = f"test_session_{uuid.uuid4().hex[:8]}"
    token_service = get_token_service()
    token = token_service.create_token(
        user_id=test_user.user_id,
        company_id=test_company.company_id,
        session_id=unique_session_id
    )
    
    subdomain = test_company.subdomain
    
    # Создаем HTTP клиент
    transport = ASGITransport(app=frontend_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"http://{subdomain}.localhost:8002",
        cookies={"auth_token": token},
        headers={"Host": f"{subdomain}.localhost:8002"}
    ) as client:
        # Добавляем ссылки на данные для использования в тестах
        client.test_user = test_user
        client.test_company = test_company
        client.test_context = test_context
        client.auth_token = token
        yield client
    
    # Очистка
    try:
        await container.user_repository.delete(test_user.user_id)
        await container.subdomain_repository.delete(test_company.subdomain)
        await container.company_repository.delete(test_company.company_id)
    except Exception:
        pass


# Фикстуры репозиториев для frontend тестов с установленным контекстом
# Используются когда нужна изоляция данных по компании frontend_client

@pytest_asyncio.fixture
async def frontend_agent_repo(frontend_app, frontend_client):
    """AgentRepository с контекстом frontend_client"""
    set_context(frontend_client.test_context)
    return frontend_app.state.agents_container.agent_repository


@pytest_asyncio.fixture
async def frontend_flow_repo(frontend_app, frontend_client):
    """FlowRepository с контекстом frontend_client"""
    set_context(frontend_client.test_context)
    return frontend_app.state.agents_container.flow_repository


@pytest_asyncio.fixture
async def frontend_tool_repo(frontend_app, frontend_client):
    """ToolRepository с контекстом frontend_client"""
    set_context(frontend_client.test_context)
    return frontend_app.state.agents_container.tool_repository


@pytest_asyncio.fixture
async def frontend_session_repo(frontend_app, frontend_client):
    """SessionRepository с контекстом frontend_client"""
    set_context(frontend_client.test_context)
    return frontend_app.state.agents_container.session_repository


@pytest_asyncio.fixture
async def frontend_mcp_repo(frontend_app, frontend_client):
    """MCPServerRepository с контекстом frontend_client"""
    set_context(frontend_client.test_context)
    return frontend_app.state.agents_container.mcp_server_repository


@pytest_asyncio.fixture
async def frontend_variable_repo(frontend_app, frontend_client):
    """VariableRepository с контекстом frontend_client"""
    set_context(frontend_client.test_context)
    return frontend_app.state.container.variable_repository


@pytest_asyncio.fixture
async def frontend_canvas_service(frontend_app, frontend_client):
    """CanvasService с контекстом frontend_client"""
    set_context(frontend_client.test_context)
    return frontend_app.state.container.canvas_service


class MockResponse:
    """Mock для httpx.Response"""

    def __init__(self, status_code: int, json_data: dict = None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text
        self.request = MagicMock()

    def json(self):
        return self._json_data

    def raise_for_status(self):
        import httpx
        if 400 <= self.status_code < 600:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=self.request,
                response=self,
            )


class MockServer:
    """
    Mock HTTP сервер для тестов

    Использование:
        server = MockServer()

        @server.get("/api/users")
        async def get_users(url: str, params: dict, **kwargs):
            return MockResponse(200, {"users": [...]})
    """

    def __init__(self):
        self.routes: Dict[tuple, Callable] = {}
        self.requests = []

    def get(self, path_pattern: str):
        """Регистрация GET эндпоинта"""
        def decorator(func: Callable):
            self.routes[("GET", path_pattern)] = func
            return func
        return decorator

    def post(self, path_pattern: str):
        """Регистрация POST эндпоинта"""
        def decorator(func: Callable):
            self.routes[("POST", path_pattern)] = func
            return func
        return decorator

    def put(self, path_pattern: str):
        """Регистрация PUT эндпоинта"""
        def decorator(func: Callable):
            self.routes[("PUT", path_pattern)] = func
            return func
        return decorator

    def delete(self, path_pattern: str):
        """Регистрация DELETE эндпоинта"""
        def decorator(func: Callable):
            self.routes[("DELETE", path_pattern)] = func
            return func
        return decorator

    def _match_route(self, method: str, url: str) -> Optional[tuple]:
        """Находит подходящий роут и извлекает параметры из URL"""
        import re
        from urllib.parse import urlparse

        path = urlparse(url).path

        for (route_method, pattern), handler in self.routes.items():
            if route_method != method:
                continue

            regex_pattern = re.sub(r'\{(\w+)\}', r'(?P<\1>[^/]+)', pattern)
            regex_pattern = f"^{regex_pattern}$"

            match = re.match(regex_pattern, path)
            if match:
                return handler, match.groupdict()

        return None

    async def request(self, method: str, url: str, params: dict = None, json: dict = None):
        """Обработка запроса"""
        self.requests.append({"method": method, "url": url, "params": params, "json": json})

        route_match = self._match_route(method, url)
        if route_match:
            handler, path_params = route_match
            return await handler(url=url, params=params or {}, json=json, path_params=path_params)

        return MockResponse(404, text="Not found")

    async def get_request(self, url: str, params: dict = None):
        """GET запрос"""
        return await self.request("GET", url, params=params)

    async def post_request(self, url: str, json: dict = None):
        """POST запрос"""
        return await self.request("POST", url, json=json)

    async def put_request(self, url: str, json: dict = None):
        """PUT запрос"""
        return await self.request("PUT", url, json=json)

    async def delete_request(self, url: str):
        """DELETE запрос"""
        return await self.request("DELETE", url)

    async def aclose(self):
        """Закрытие соединения"""
        pass


@pytest_asyncio.fixture
async def mock_server():
    """Mock HTTP сервер для тестов"""
    return MockServer()


class TestHelpers:
    """Вспомогательные функции для тестов"""

    @staticmethod
    async def create_simple_agent(
        agent_id: str,
        name: str,
        prompt: str,
        tools: list = None
    ) -> AgentConfig:
        """Создать простой ReAct агент для тестов"""
        agent_config = AgentConfig(
            agent_id=agent_id,
            name=name,
            description=f"Test agent: {name}",
            type=AgentType.REACT,
            code_mode=CodeMode.CODE_REFERENCE,
            function_class=None,
            prompt=prompt,
            tools=tools or [],
            llm_config=LLMConfig(model="mock-gpt-4", context_window=10000),
            source="test"
        )

        agent_repo = get_agents_container().agent_repository
        await agent_repo.set(agent_config)
        return agent_config

    @staticmethod
    async def create_simple_flow(
        flow_id: str,
        name: str,
        entry_point_agent: str
    ) -> FlowConfig:
        """Создать простой Flow для тестов"""
        flow_config = FlowConfig(
            flow_id=flow_id,
            name=name,
            description=f"Test flow: {name}",
            entry_point_agent=entry_point_agent,
            source="test"
        )

        flow_repo = get_agents_container().flow_repository
        await flow_repo.set(flow_config)
        return flow_config

    @staticmethod
    def create_inline_tool(
        tool_id: str,
        function_name: str,
        function_body: str,
        description: str = ""
    ) -> ToolReference:
        """Создать inline tool для тестов (все тулы async)"""
        # Конвертируем def в async def если нужно (но не дублируем async)
        if "async def " not in function_body:
            async_body = function_body.replace("def ", "async def ", 1)
        else:
            async_body = function_body
        
        inline_code = f'''
from apps.agents.services.tool_decorator import tool

@tool
{async_body}
'''

        return ToolReference(
            tool_id=tool_id,
            code_mode=CodeMode.INLINE_CODE,
            inline_code=inline_code.strip(),
            description=description or f"Test tool: {tool_id}"
        )


@pytest_asyncio.fixture
async def test_helpers():
    """Вспомогательные функции для тестов"""
    return TestHelpers


@pytest_asyncio.fixture(scope="session")
async def taskiq_broker(migrated_db):
    """Инициализирует PostgreSQL TaskIQ broker для всей сессии тестов"""
    from core.tasks.broker import broker
    
    await broker.startup()
    logger.info("✅ TaskIQ PostgreSQL broker запущен для сессии тестов")
    
    yield broker
    
    await broker.shutdown()
    logger.info("✅ TaskIQ PostgreSQL broker остановлен")


@pytest_asyncio.fixture
async def payment_service(migrated_db):
    """PaymentService для тестов"""
    container = get_agents_container()
    return container.payment_service


@pytest_asyncio.fixture
async def billing_service(migrated_db):
    """BillingService для тестов"""
    container = get_agents_container()
    return container.billing_service


@pytest_asyncio.fixture
async def yoomoney_provider():
    """YooMoney провайдер для интеграционных тестов платежей"""
    from core.clients.payment.yoomoney_provider import YooMoneyProvider, YooMoneyConfig

    config = YooMoneyConfig(
        provider_type="yoomoney",
        enabled=True,
        account_number="4100119360332365",
        notification_secret="test_integration_secret_key_12345",
        quickpay_url="https://yoomoney.ru/quickpay/confirm.xml"
    )
    return YooMoneyProvider(config)


@pytest_asyncio.fixture
async def auth_service(storage: Storage):
    """AuthService для тестов аутентификации"""
    container = get_agents_container()
    return container.auth_service


@pytest_asyncio.fixture
async def mock_provider():
    """Mock провайдер платежей для тестов"""
    from unittest.mock import Mock, AsyncMock
    from core.clients.payment.base_provider import (
        BasePaymentProvider,
        PaymentResponse
    )

    provider = Mock(spec=BasePaymentProvider)
    provider.provider_name = "yoomoney"
    provider.create_payment = AsyncMock(return_value=PaymentResponse(
        payment_url="https://yoomoney.ru/quickpay/confirm.xml?params",
        external_payment_id=None,
        metadata={"provider": "yoomoney"}
    ))
    return provider


def skip_if_no_external_access(e: Exception = None, message: str = None):
    """Пропускает тест, если нет доступа к внешнему серверу или ошибка авторизации"""
    if message:
        # Прямая проверка текста сообщения
        msg_lower = message.lower()
        if "unauthorized" in msg_lower or "forbidden" in msg_lower or "api key" in msg_lower:
            pytest.skip(f"Ошибка авторизации внешнего сервиса: {message[:100]}")
    
    if e is None:
        return
        
    import httpx
    error_str = str(e).lower()
    
    # Проверка на ошибки сети
    if (
        "event loop is closed" in str(e) or
        "connect" in error_str or
        "timeout" in error_str or
        isinstance(e, (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError, RuntimeError))
    ):
        pytest.skip(f"Нет доступа к внешнему серверу: {e}")
    
    # Проверка на ошибки авторизации
    if "unauthorized" in error_str or "forbidden" in error_str or "api key" in error_str:
        pytest.skip(f"Ошибка авторизации внешнего сервиса: {e}")
    
    raise


# === Фикстуры для E2E тестов с процессами ===

import subprocess
import sys
import socket
import time
import multiprocessing


def _get_free_port() -> int:
    """Получить свободный порт"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _wait_for_server(host: str, port: int, timeout: float = 30.0) -> bool:
    """Ждать пока сервер станет доступен"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def _get_localhost_env() -> dict:
    """Переменные окружения для localhost - используем conf.local.json"""
    return os.environ.copy()


def _run_agents_server(host: str, port: int):
    """Запуск agents сервера (для multiprocessing)"""
    import uvicorn
    # Используем строковый путь для корректной работы multiprocessing
    uvicorn.run("apps.agents.main:app", host=host, port=port, log_level="warning")


def _run_frontend_server(host: str, port: int):
    """Запуск frontend сервера (для multiprocessing)"""
    import uvicorn
    # Используем строковый путь для корректной работы multiprocessing
    uvicorn.run("apps.frontend.main:app", host=host, port=port, log_level="warning")


@pytest.fixture(scope="session")
def taskiq_worker_process(migrated_db):
    """
    Запускает TaskIQ воркер в отдельном subprocess.
    Session scope - один воркер на всю сессию тестов.
    """
    project_root = Path(__file__).parent.parent
    env = _get_localhost_env()
    
    # Запускаем воркер без перехвата stdout/stderr для отладки
    process = subprocess.Popen(
        [sys.executable, "-m", "taskiq", "worker", "core.tasks.worker:broker", "--workers", "1"],
        cwd=str(project_root),
        env=env
    )
    
    # Даем воркеру время на инициализацию
    time.sleep(5)
    
    if process.poll() is not None:
        raise RuntimeError(f"TaskIQ воркер не запустился (exit code: {process.returncode})")
    
    logger.info(f"✅ TaskIQ воркер запущен (PID: {process.pid})")
    
    yield process
    
    process.terminate()
    try:
        process.wait(timeout=5)
    except:
        process.kill()
    logger.info("✅ TaskIQ воркер остановлен")


@pytest.fixture(scope="session")
def agents_server_process(migrated_db):
    """
    Запускает agents сервер в отдельном процессе.
    Session scope - один сервер на всю сессию тестов.
    """
    port = _get_free_port()
    host = "127.0.0.1"
    
    server_process = multiprocessing.Process(
        target=_run_agents_server,
        args=(host, port),
        daemon=True
    )
    server_process.start()
    
    if not _wait_for_server(host, port, timeout=30):
        server_process.terminate()
        raise RuntimeError(f"Agents сервер не запустился на {host}:{port}")
    
    logger.info(f"✅ Agents сервер запущен на http://{host}:{port}")
    
    yield {"host": host, "port": port, "url": f"http://{host}:{port}"}
    
    server_process.terminate()
    server_process.join(timeout=5)
    logger.info("✅ Agents сервер остановлен")


@pytest.fixture(scope="session")
def agents_service(agents_server_process):
    """
    Алиас для agents_server_process с установкой переменных окружения.
    Используется для межсервисного взаимодействия в тестах.
    """
    import os
    host = agents_server_process["host"]
    port = agents_server_process["port"]
    
    os.environ["AGENTS_SERVICE_HOST"] = host
    os.environ["AGENTS_SERVICE_PORT"] = str(port)
    os.environ["TEST_AGENTS_SERVICE_URL"] = agents_server_process["url"]
    
    return agents_server_process


@pytest.fixture(scope="session")
def frontend_server_process(migrated_db):
    """
    Запускает frontend сервер в отдельном процессе.
    Session scope - один сервер на всю сессию тестов.
    """
    port = _get_free_port()
    host = "127.0.0.1"
    
    server_process = multiprocessing.Process(
        target=_run_frontend_server,
        args=(host, port),
        daemon=True
    )
    server_process.start()
    
    if not _wait_for_server(host, port, timeout=30):
        server_process.terminate()
        raise RuntimeError(f"Frontend сервер не запустился на {host}:{port}")
    
    logger.info(f"✅ Frontend сервер запущен на http://{host}:{port}")
    
    yield {"host": host, "port": port, "url": f"http://{host}:{port}"}
    
    server_process.terminate()
    server_process.join(timeout=5)
    logger.info("✅ Frontend сервер остановлен")
