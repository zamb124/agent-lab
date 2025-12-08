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

# Три БД как на продакшне
os.environ.setdefault("DATABASE__URL", "postgresql+asyncpg://agent_user:agent_password@localhost:5432/agents_db")
os.environ.setdefault("DATABASE__SHARED_URL", "postgresql+asyncpg://agent_user:agent_password@localhost:5432/shared_db")
os.environ.setdefault("DATABASE__CRM_URL", "postgresql+asyncpg://agent_user:agent_password@localhost:5432/crm_db")
os.environ.setdefault("SERVER__DEBUG", "true")
os.environ.setdefault("LLM__DEFAULT_MODEL", "mock-gpt-4")
os.environ.setdefault("LLM__OPENROUTER__ENABLED", "true")
os.environ.setdefault("LLM__OPENROUTER__API_KEY", "test-openrouter-key")
os.environ.setdefault("AUTH__JWT_SECRET_KEY", "test-jwt-secret-key-for-tests-only")
os.environ.setdefault("S3__ENABLED", "true")
os.environ.setdefault("S3__DEFAULT_BUCKET", "vkbucket")

# Теперь можно импортировать модули
from core.db import Storage
from core.context import set_context, clear_context
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
    
    Необходимо для корректной работы Redis broker в TaskIQ -
    все соединения должны быть в одном event loop.
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
        from sqlalchemy import text
        # Service БД (agents_db): storage, stores, agent_states, otel_spans
        await create_tables(
            db_url=settings.database.url,
            table_names=["storage", "stores", "agent_states", "otel_spans"]
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
        # Shared БД (shared_db): users, storage, variables, usage
        if settings.database.shared_url:
            await create_tables(
                db_url=settings.database.shared_url,
                table_names=["users", "storage", "variables", "usage"]
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
        ),
        container=get_agents_container()
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
        groups=["admin"],
        companies={test_company.company_id: ["admin"]},
        active_company_id=test_company.company_id
    )


@pytest_asyncio.fixture
async def test_context(test_user: User, test_company: Company, migrated_db, company_repo, user_repo):
    """Тестовый контекст для тестов (используется явно где нужен полный контекст)

    Добавляй в параметры теста если нужен контекст с пользователем и компанией.
    Каждый тест получает уникальный session_id для изоляции.
    
    Сохраняет test_company и test_user в БД для межсервисного взаимодействия.
    Создает auth_token для HTTPRepositoryProxy.
    """
    from core.utils.tokens import get_token_service
    
    # Сохраняем компанию и пользователя в БД для доступа из других процессов (agents_service)
    await company_repo.set(test_company)
    await user_repo.set(test_user)
    
    unique_session_id = f"test_session_{uuid.uuid4().hex[:8]}"
    
    # Создаем JWT токен для межсервисной авторизации
    token_service = get_token_service()
    roles = test_user.companies.get(test_company.company_id, ["admin"])
    auth_token = token_service.create_token(
        user_id=test_user.user_id,
        company_id=test_company.company_id,
        roles=roles,
        session_id=unique_session_id,
    )
    
    context = Context(
        user=test_user,
        session_id=unique_session_id,
        platform="api",
        active_company=test_company,
        user_companies=[test_company],
        metadata={},
        auth_token=auth_token,
        container=get_agents_container(),
    )

    set_context(context)
    yield context

    clear_context()
    # Очистка после теста
    try:
        await user_repo.delete(test_user.user_id)
        await company_repo.delete(test_company.company_id)
    except Exception:
        pass


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


@pytest_asyncio.fixture
async def agents_client(agents_app, test_context, test_user, test_company):
    """
    HTTP клиент для тестирования agents API с авторизацией.
    
    Создает JWT токен и передает его в cookies/headers для авторизации.
    Передает X-Company-Id для определения компании.
    """
    import httpx
    from httpx import ASGITransport
    from core.utils.tokens import get_token_service
    from core.db.repositories.subdomain_repository import SubdomainMapping
    
    container = agents_app.state.container
    
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
    roles = test_user.companies.get(test_company.company_id, ["admin"])
    token = token_service.create_token(
        user_id=test_user.user_id,
        company_id=test_company.company_id,
        roles=roles,
        session_id=unique_session_id,
    )
    
    # Создаем HTTP клиент с авторизацией
    transport = ASGITransport(app=agents_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={"auth_token": token},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Company-Id": test_company.company_id,
        }
    ) as client:
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


@pytest_asyncio.fixture(scope="session")
async def frontend_app(migrated_db):
    """FastAPI приложение для frontend сервиса (порт 8002)"""
    from apps.frontend.main import create_app, _mount_static_files
    from apps.frontend.core.plugin_loader import discover_and_load_plugins
    
    app = create_app()
    
    # Загружаем плагины вручную т.к. lifespan не выполняется при ASGITransport
    await discover_and_load_plugins(app)
    
    # Монтируем статические файлы
    _mount_static_files(app)
    
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
    roles = test_user.companies.get(test_company.company_id, ["admin"])
    token = token_service.create_token(
        user_id=test_user.user_id,
        company_id=test_company.company_id,
        roles=roles,
        session_id=unique_session_id,
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
    """Инициализирует Redis TaskIQ broker для всей сессии тестов"""
    from core.tasks.broker import broker
    
    await broker.startup()
    logger.info("TaskIQ Redis broker запущен для сессии тестов")
    
    yield broker
    
    await broker.shutdown()
    logger.info("TaskIQ Redis broker остановлен")


@pytest_asyncio.fixture(scope="session")
async def taskiq_schedule_source(migrated_db):
    """Инициализирует Redis TaskIQ schedule source для отложенных задач"""
    from core.tasks.broker import schedule_source
    
    await schedule_source.startup()
    logger.info("TaskIQ schedule source запущен для сессии тестов")
    
    yield schedule_source
    
    await schedule_source.shutdown()
    logger.info("TaskIQ schedule source остановлен")


@pytest_asyncio.fixture(scope="session")
async def taskiq_scheduler(taskiq_broker, taskiq_schedule_source):
    """TaskIQ scheduler для отложенных задач (зависит от broker и schedule_source)"""
    from core.tasks.broker import scheduler
    
    logger.info("TaskIQ scheduler готов к использованию")
    
    yield scheduler


@pytest_asyncio.fixture
async def taskiq_environment(taskiq_broker, taskiq_schedule_source, taskiq_scheduler):
    """
    Полное окружение TaskIQ для тестов: broker + schedule_source + scheduler.
    Используйте эту фикстуру когда нужно всё вместе.
    """
    yield {
        "broker": taskiq_broker,
        "schedule_source": taskiq_schedule_source,
        "scheduler": taskiq_scheduler,
    }


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


def _get_free_port() -> int:
    """Получить свободный порт"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _wait_for_server(host: str, port: int, timeout: float = 45.0, process: subprocess.Popen = None) -> bool:
    """
    Ждать пока сервер станет доступен.
    Проверяет что процесс жив во время ожидания.
    """
    start = time.time()
    while time.time() - start < timeout:
        # Проверяем что процесс ещё жив
        if process and process.poll() is not None:
            logger.error(f"Процесс сервера умер (exit code: {process.returncode})")
            return False
        
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def _get_localhost_env() -> dict:
    """Переменные окружения для localhost - используем conf.local.json"""
    return os.environ.copy()


def _start_server_subprocess(app_path: str, host: str, port: int, name: str) -> subprocess.Popen:
    """
    Запускает сервер через subprocess (надежнее чем multiprocessing на macOS).
    """
    project_root = Path(__file__).parent.parent
    env = _get_localhost_env()
    
    cmd = [
        sys.executable, "-m", "uvicorn",
        app_path,
        "--host", host,
        "--port", str(port),
        "--log-level", "warning"
    ]
    
    # Не используем PIPE чтобы избежать блокировки при заполнении буфера
    process = subprocess.Popen(
        cmd,
        cwd=str(project_root),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    
    logger.info(f"Запускаем {name} на {host}:{port} (PID: {process.pid})")
    return process


@pytest.fixture(scope="session")
def taskiq_worker_process(migrated_db):
    """
    Запускает TaskIQ воркер в отдельном subprocess.
    Session scope - один воркер на всю сессию тестов.
    """
    project_root = Path(__file__).parent.parent
    env = _get_localhost_env()
    
    # Запускаем воркер с apps.worker:broker чтобы все задачи были зарегистрированы
    process = subprocess.Popen(
        [sys.executable, "-m", "taskiq", "worker", "apps.worker:broker", "--workers", "1"],
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
def agents_server_process(session_test_data):
    """
    Запускает agents сервер через subprocess.
    Session scope - один сервер на всю сессию тестов.
    Зависит от session_test_data чтобы данные были в БД до запуска.
    """
    port = _get_free_port()
    host = "127.0.0.1"
    
    process = _start_server_subprocess(
        "apps.agents.main:app",
        host, port,
        "Agents сервер"
    )
    
    if not _wait_for_server(host, port, timeout=45, process=process):
        process.terminate()
        raise RuntimeError(f"Agents сервер не запустился на {host}:{port}")
    
    logger.info(f"✅ Agents сервер запущен на http://{host}:{port}")
    
    yield {"host": host, "port": port, "url": f"http://{host}:{port}"}
    
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
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


@pytest_asyncio.fixture(scope="session")
async def session_test_data(migrated_db):
    """
    Session-scoped тестовые данные для межсервисного взаимодействия.
    Создает user/company в shared БД ДО запуска subprocess сервисов.
    """
    from core.models.identity_models import User, UserStatus, AuthProvider
    from core.models.billing_models import TariffPlan
    from core.db.repositories.subdomain_repository import SubdomainMapping
    from core.utils.tokens import get_token_service
    
    container = get_agents_container()
    
    session_company = Company(
        company_id="test_session_company",
        subdomain="test_session",
        name="Test Session Company",
        tariff_plan=TariffPlan.ENTERPRISE,
        balance=100000.0,
        monthly_budget=50000.0,
        current_month_spent=0.0,
        status="active"
    )
    
    session_user = User(
        user_id="test_session_user",
        provider=AuthProvider.YANDEX,
        provider_user_id="session_test",
        email="session@test.com",
        name="Session Test User",
        status=UserStatus.ACTIVE,
        groups=["admin"],
        companies={"test_session_company": ["admin"]},
        active_company_id="test_session_company",
    )
    
    await container.company_repository.set(session_company)
    await container.user_repository.set(session_user)
    
    subdomain_mapping = SubdomainMapping(
        subdomain=session_company.subdomain,
        company_id=session_company.company_id
    )
    await container.subdomain_repository.set(subdomain_mapping)
    
    # Создаем sharing users для тестов API
    import json
    sharing_users_data = [
        ("sharing_user_alice", "Alice Sharing", "alice.sharing@testmail.com"),
        ("sharing_user_bob", "Bob Sharing", "bob.sharing@testmail.com"),
        ("sharing_user_charlie", "Charlie Sharing", "charlie.sharing@testmail.com"),
    ]
    for user_id, name, email in sharing_users_data:
        sharing_user = User(
            user_id=user_id,
            provider=AuthProvider.GOOGLE,
            provider_user_id=f"provider_{user_id}",
            email=email,
            name=name,
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={session_company.company_id: ["member"]},
            active_company_id=session_company.company_id,
        )
        await container.user_repository.set(sharing_user)
        
        providers_key = f"user_providers:{user_id}"
        providers_data = {
            f"provider_{user_id}": {
                "provider_name": "google",
                "email": email,
                "avatar_url": None,
                "metadata": {}
            }
        }
        await container.shared_storage.set(providers_key, json.dumps(providers_data), force_global=True)
    
    token_service = get_token_service()
    token = token_service.create_token(
        user_id=session_user.user_id,
        company_id=session_company.company_id,
        roles=["admin"],
    )
    
    logger.info("✅ Session test data created for cross-service tests")
    
    yield {
        "user": session_user,
        "company": session_company,
        "token": token,
        "headers": {
            "Authorization": f"Bearer {token}",
            "X-Company-Id": session_company.company_id,
        }
    }
    
    # Cleanup
    try:
        await container.user_repository.delete(session_user.user_id)
        await container.subdomain_repository.delete(session_company.subdomain)
        await container.company_repository.delete(session_company.company_id)
    except Exception:
        pass


@pytest.fixture(scope="session")
def crm_server_process(session_test_data, agents_server_process):
    """
    Запускает CRM сервер через subprocess.
    Session scope - один сервер на всю сессию тестов.
    Зависит от session_test_data чтобы данные были в БД до запуска.
    Зависит от agents_server_process для AI вызовов.
    """
    # Устанавливаем URL Agents сервиса (server.agents_service_url)
    os.environ["SERVER__AGENTS_SERVICE_URL"] = agents_server_process["url"]
    
    port = _get_free_port()
    host = "127.0.0.1"
    
    process = _start_server_subprocess(
        "apps.crm.main:app",
        host, port,
        "CRM сервер"
    )
    
    if not _wait_for_server(host, port, timeout=45, process=process):
        process.terminate()
        raise RuntimeError(f"CRM сервер не запустился на {host}:{port}")
    
    url = f"http://{host}:{port}"
    logger.info(f"✅ CRM сервер запущен на {url}")
    
    os.environ["TEST_CRM_SERVICE_URL"] = url
    
    yield {"host": host, "port": port, "url": url, "test_data": session_test_data}
    
    os.environ.pop("TEST_CRM_SERVICE_URL", None)
    os.environ.pop("SERVER__AGENTS_SERVICE_URL", None)
    
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
    logger.info("✅ CRM сервер остановлен")


@pytest_asyncio.fixture
async def crm_frontend_client(frontend_app, session_test_data, crm_server_process):
    """
    HTTP клиент для тестирования CRM partials через frontend.
    Использует session_test_data для авторизации (данные уже в shared БД).
    """
    import httpx
    from httpx import ASGITransport
    
    user = session_test_data["user"]
    company = session_test_data["company"]
    token = session_test_data["token"]
    
    transport = ASGITransport(app=frontend_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"http://{company.subdomain}.localhost:8002",
        cookies={"auth_token": token},
        headers={
            "Host": f"{company.subdomain}.localhost:8002",
            "Authorization": f"Bearer {token}",
            "X-Company-Id": company.company_id,
        }
    ) as client:
        client.test_user = user
        client.test_company = company
        client.auth_token = token
        yield client



@pytest_asyncio.fixture
async def service_auth_headers(test_user, test_company, user_repo, company_repo):
    """
    Заголовки авторизации для межсервисных запросов.
    Создает JWT токен и сохраняет пользователя/компанию в БД.
    """
    from core.utils.tokens import get_token_service
    
    # Сохраняем в shared БД для доступа из agents_service
    await company_repo.set(test_company)
    await user_repo.set(test_user)
    
    token_service = get_token_service()
    token = token_service.create_token(
        user_id=test_user.user_id,
        company_id=test_company.company_id,
        roles=["admin"],
        metadata={"service": "test"}
    )
    
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Company-Id": test_company.company_id,
    }
    
    yield headers
    
    # Очистка
    try:
        await user_repo.delete(test_user.user_id)
        await company_repo.delete(test_company.company_id)
    except Exception:
        pass


# === CRM Service Fixtures ===

@pytest_asyncio.fixture(scope="session")
async def crm_app(migrated_db, agents_server_process):
    """
    FastAPI приложение для CRM сервиса (порт 8003).
    
    Зависит от agents_server_process чтобы CRM мог вызывать AI сервис.
    """
    # Устанавливаем URL agents сервиса ДО создания приложения
    os.environ["SERVER__AGENTS_SERVICE_URL"] = agents_server_process["url"]
    
    # Сбрасываем кэш CRM settings чтобы подхватить новый URL
    import apps.crm.config as crm_config_module
    crm_config_module._crm_settings = None
    
    from apps.crm.main import create_app
    
    app = create_app()
    
    # Инициализируем через on_startup (включает file_processors)
    container = app.state.container
    settings = app.state.settings
    
    # Вызываем on_startup вручную (lifespan не выполняется с ASGITransport)
    from apps.crm.main import on_startup
    await on_startup(app, container, settings)
    
    return app


@pytest_asyncio.fixture
async def crm_client(crm_app, test_context, test_user, test_company):
    """
    HTTP клиент для тестирования CRM API с авторизацией.
    """
    import httpx
    from httpx import ASGITransport
    from core.utils.tokens import get_token_service
    
    container = crm_app.state.container
    
    # Сохраняем компанию и пользователя
    await container.company_repository.set(test_company)
    await container.user_repository.set(test_user)
    
    # Создаем JWT токен
    unique_session_id = f"test_session_{uuid.uuid4().hex[:8]}"
    token_service = get_token_service()
    roles = test_user.companies.get(test_company.company_id, ["admin"])
    token = token_service.create_token(
        user_id=test_user.user_id,
        company_id=test_company.company_id,
        roles=roles,
        session_id=unique_session_id,
    )
    
    transport = ASGITransport(app=crm_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={"auth_token": token},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Company-Id": test_company.company_id,
        }
    ) as client:
        client.test_user = test_user
        client.test_company = test_company
        client.test_context = test_context
        client.auth_token = token
        yield client
    
    # Очистка
    try:
        await container.user_repository.delete(test_user.user_id)
        await container.company_repository.delete(test_company.company_id)
    except Exception:
        pass


@pytest.fixture(scope="session")
def frontend_server_process(migrated_db):
    """
    Запускает frontend сервер через subprocess.
    Session scope - один сервер на всю сессию тестов.
    """
    port = _get_free_port()
    host = "127.0.0.1"
    
    process = _start_server_subprocess(
        "apps.frontend.main:app",
        host, port,
        "Frontend сервер"
    )
    
    if not _wait_for_server(host, port, timeout=45, process=process):
        process.terminate()
        raise RuntimeError(f"Frontend сервер не запустился на {host}:{port}")
    
    logger.info(f"Frontend сервер запущен на http://{host}:{port}")
    
    yield {"host": host, "port": port, "url": f"http://{host}:{port}"}
    
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
    logger.info("Frontend сервер остановлен")


# === CRM Database & Container ===

@pytest_asyncio.fixture(scope="session")
async def crm_db(migrated_db):
    """
    CRM Database для тестов.
    Создает таблицы CRM в отдельной БД crm_db.
    """
    from core.config import get_settings
    from apps.crm.db.base import CRMDatabase
    
    settings = get_settings()
    crm_db_url = settings.database.crm_url or settings.database.url
    
    db = CRMDatabase(crm_db_url)
    await db.create_tables(drop_existing=True)
    
    yield db
    
    CRMDatabase.reset()


@pytest_asyncio.fixture(scope="session")
async def crm_container(crm_db, migrated_db):
    """
    CRM Container для тестов.
    Session scope - переиспользуется между тестами.
    """
    from core.config import get_settings
    from apps.crm.container import CRMContainer, set_crm_container, reset_crm_container
    
    settings = get_settings()
    crm_db_url = settings.database.crm_url or settings.database.url
    
    container = CRMContainer(
        db_url=crm_db_url,
        shared_db_url=settings.database.shared_url
    )
    set_crm_container(container)
    
    await container.entity_type_service.init_system_types()
    
    yield container
    
    reset_crm_container()


# === CRM Repositories ===

@pytest_asyncio.fixture
async def entity_type_repo(crm_container):
    """EntityTypeRepository"""
    return crm_container.entity_type_repository


@pytest_asyncio.fixture
async def relationship_repo(crm_container):
    """RelationshipRepository"""
    return crm_container.relationship_repository


@pytest_asyncio.fixture
async def note_repo(crm_container):
    """NoteRepository"""
    return crm_container.note_repository


@pytest_asyncio.fixture
async def task_repo(crm_container):
    """TaskRepository"""
    return crm_container.task_repository


@pytest_asyncio.fixture
async def company_mapping_repo(crm_container):
    """CompanyMappingRepository"""
    return crm_container.company_mapping_repository


# === CRM Services ===

@pytest_asyncio.fixture
async def entity_type_service(crm_container):
    """EntityTypeService"""
    return crm_container.entity_type_service


@pytest_asyncio.fixture
async def note_service(crm_container):
    """NoteService"""
    return crm_container.note_service


@pytest_asyncio.fixture
async def task_service(crm_container):
    """TaskService"""
    return crm_container.task_service


@pytest_asyncio.fixture
async def relationship_service(crm_container):
    """RelationshipService"""
    return crm_container.relationship_service


@pytest_asyncio.fixture
async def entity_service(crm_container):
    """EntityService"""
    return crm_container.entity_service


@pytest_asyncio.fixture
async def graph_service(crm_container):
    """GraphService"""
    return crm_container.graph_service


# === CRM Sample Objects ===

@pytest_asyncio.fixture
async def sample_entity_type(test_context, entity_type_repo, unique_id):
    """Создает тестовый тип сущности"""
    from apps.crm.db.models import EntityType
    
    type_id = unique_id("type")
    entity_type = EntityType(
        type_id=type_id,
        company_id=test_context.active_company.company_id,
        name="Test Entity Type",
        description="Test description",
        prompt="Test extraction prompt",
        required_fields={"name": {"label": "Name", "type": "text"}},
        optional_fields={"email": {"label": "Email", "type": "email"}, "phone": {"label": "Phone", "type": "phone"}},
        icon="ti-test",
        color="#FF0000",
        is_system=False,
        check_duplicates=True,
        is_filtered=False,
    )
    
    await entity_type_repo.create(entity_type)
    yield entity_type
    
    await entity_type_repo.delete(type_id)


@pytest_asyncio.fixture
async def sample_note(test_context, note_repo, unique_id):
    """Создает тестовую заметку"""
    from datetime import date, datetime, timezone
    from apps.crm.db.models import Note
    
    note_id = unique_id("note")
    note = Note(
        note_id=note_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Test Note",
        content="This is a test note content",
        note_type="freeform",
        note_date=date.today(),
        ai_summary=None,
        linked_entity_ids=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    await note_repo.create(note)
    yield note
    
    await note_repo.delete(note_id)


@pytest_asyncio.fixture
async def sample_task(test_context, task_repo, unique_id):
    """Создает тестовую задачу"""
    from datetime import date, datetime, timezone
    from apps.crm.db.models import Task
    
    task_id = unique_id("task")
    task = Task(
        task_id=task_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Test Task",
        description="Test task description",
        priority="medium",
        status="pending",
        due_date=date.today(),
        linked_entity_id=None,
        source_note_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    await task_repo.create(task)
    yield task
    
    await task_repo.delete(task_id)


@pytest_asyncio.fixture
async def sample_relationship(test_context, relationship_repo, unique_id):
    """Создает тестовую связь"""
    from datetime import datetime, timezone
    from apps.crm.db.models import Relationship
    
    rel_id = unique_id("rel")
    relationship = Relationship(
        relationship_id=rel_id,
        company_id=test_context.active_company.company_id,
        source_entity_id=f"entity_{unique_id('src')}",
        target_entity_id=f"entity_{unique_id('tgt')}",
        relationship_type="connected_to",
        weight=1.0,
        attributes={},
        created_at=datetime.now(timezone.utc),
    )
    
    await relationship_repo.create(relationship)
    yield relationship
    
    await relationship_repo.delete(rel_id)


# === CRM Test Objects ===

@pytest_asyncio.fixture
async def test_note(crm_container, test_context):
    """Тестовая заметка для API тестов"""
    from datetime import date
    from apps.crm.db.models import Note
    
    user = test_context.user
    company = test_context.active_company
    
    note = Note(
        note_id=f"test_note_{uuid.uuid4().hex[:8]}",
        company_id=company.company_id,
        user_id=user.user_id,
        title="Test Note for API",
        content="This is test content",
        note_type="freeform",
        note_date=date.today(),
        visibility="public",
    )
    
    created = await crm_container.note_repository.create(note)
    yield created
    
    try:
        await crm_container.note_repository.delete(created.note_id)
    except Exception:
        pass


@pytest_asyncio.fixture
async def test_meeting_note(crm_container, test_context):
    """Тестовая заметка meeting_minutes"""
    from datetime import date
    from apps.crm.db.models import Note
    
    user = test_context.user
    company = test_context.active_company
    
    note = Note(
        note_id=f"test_meeting_{uuid.uuid4().hex[:8]}",
        company_id=company.company_id,
        user_id=user.user_id,
        title="Test Meeting Note",
        content="Meeting with John and Jane from ACME Corp",
        note_type="meeting_minutes",
        note_date=date.today(),
        visibility="public",
    )
    
    created = await crm_container.note_repository.create(note)
    yield created
    
    try:
        await crm_container.note_repository.delete(created.note_id)
    except Exception:
        pass


@pytest_asyncio.fixture
async def test_task(crm_container, test_context):
    """Тестовая задача для API тестов"""
    from datetime import date
    from apps.crm.db.models import Task
    
    user = test_context.user
    company = test_context.active_company
    
    task = Task(
        task_id=f"test_task_{uuid.uuid4().hex[:8]}",
        company_id=company.company_id,
        user_id=user.user_id,
        title="Test Task for API",
        description="Test description",
        priority="medium",
        status="pending",
        due_date=date.today(),
    )
    
    created = await crm_container.task_repository.create(task)
    yield created
    
    try:
        await crm_container.task_repository.delete(created.task_id)
    except Exception:
        pass


@pytest_asyncio.fixture
async def test_entity(crm_container, test_context):
    """Тестовая сущность для API тестов"""
    from apps.crm.models.entity_models import EntityCreate
    
    company = test_context.active_company
    
    entity_data = EntityCreate(
        name=f"Test Entity {uuid.uuid4().hex[:6]}",
        type="person",
        attributes={"email": "test@example.com"},
    )
    
    entity = await crm_container.entity_service.create_entity(
        entity_data, 
        company_id=company.company_id
    )
    yield entity
    
    try:
        await crm_container.entity_service.delete_entity(
            entity.entity_id, 
            company_id=company.company_id
        )
    except Exception:
        pass


# === CRM API Fixtures ===

@pytest.fixture
def test_user_id(session_test_data):
    """ID тестового пользователя для API тестов"""
    return session_test_data["user"].user_id


@pytest.fixture
def test_company_id(session_test_data):
    """ID тестовой компании для API тестов"""
    return session_test_data["company"].company_id


# === E2E Browser Fixtures ===

FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "8002"))
E2E_USER_ID = "e2e_browser_test_user"
E2E_COMPANY_ID = "e2e_browser_test_company"
E2E_SESSION_ID = "e2e_browser_test_session"
E2E_SUBDOMAIN = "e2ebrowser"


def pytest_collection_modifyitems(items):
    """Группирует все browser тесты в один xdist worker."""
    for item in items:
        if "/browser/" in str(item.fspath):
            item.add_marker(pytest.mark.xdist_group("browser"))


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Сохраняем результат теста для использования в фикстурах"""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


@pytest.fixture(scope="session")
def e2e_test_data(migrated_db):
    """Данные тестового пользователя для E2E тестов."""
    return {
        "user_id": E2E_USER_ID,
        "company_id": E2E_COMPANY_ID,
        "session_id": E2E_SESSION_ID,
        "subdomain": E2E_SUBDOMAIN,
    }


@pytest.fixture(scope="session")
def live_server(migrated_db, e2e_test_data, taskiq_worker_process, agents_service, frontend_server_process):
    """Frontend сервер для E2E тестов."""
    return frontend_server_process


@pytest.fixture(scope="session")
def e2e_auth_token(e2e_test_data):
    """JWT токен для e2e тестов"""
    from core.utils.tokens import get_token_service
    
    token_service = get_token_service()
    token = token_service.create_token(
        user_id=e2e_test_data["user_id"],
        company_id=e2e_test_data["company_id"],
        expires_in=86400
    )
    return token


@pytest.fixture(scope="session")
def e2e_base_url(live_server, e2e_test_data):
    """Базовый URL для E2E тестов с поддоменом компании."""
    subdomain = e2e_test_data["subdomain"]
    return f"http://{subdomain}.localhost:{live_server['port']}"


@pytest.fixture(scope="session")
def server_url(live_server):
    """URL сервера для публичных страниц (без поддомена)."""
    return f"http://localhost:{live_server['port']}"


# === Playwright Fixtures ===

@pytest_asyncio.fixture(scope="session")
async def browser(playwright):
    """Запускает браузер один раз на всю сессию"""
    headless = os.getenv("HEADED", "false").lower() != "true"
    browser = await playwright.chromium.launch(headless=headless)
    yield browser
    await browser.close()


@pytest_asyncio.fixture(scope="function")
async def context(browser, e2e_auth_token, e2e_base_url, e2e_test_data):
    """Создает новый контекст браузера для каждого теста с авторизацией"""
    subdomain = e2e_test_data["subdomain"]
    
    context = await browser.new_context(
        base_url=e2e_base_url,
        viewport={"width": 1280, "height": 720},
    )
    
    await context.add_cookies([{
        "name": "auth_token",
        "value": e2e_auth_token,
        "domain": f"{subdomain}.localhost",  
        "path": "/",
    }])
    
    yield context
    await context.close()


@pytest_asyncio.fixture(scope="function")
async def page(context):
    """Создает новую страницу в контексте"""
    from playwright.async_api import Page
    page = await context.new_page()
    yield page
    await page.close()


@pytest_asyncio.fixture(scope="function")
async def authenticated_page(page, e2e_base_url):
    """Страница с проверкой авторизации."""
    await page.goto(e2e_base_url)
    await page.wait_for_load_state("networkidle")
    
    if "/auth" in page.url:
        raise AssertionError("Пользователь не авторизован - редирект на /auth")
    
    yield page


@pytest_asyncio.fixture(scope="function")
async def public_page(browser, live_server):
    """Страница БЕЗ авторизации для тестирования публичных страниц."""
    from playwright.async_api import Page
    
    context = await browser.new_context(
        base_url=f"http://localhost:{live_server['port']}",
        viewport={"width": 1280, "height": 720},
    )
    
    page = await context.new_page()
    yield page
    
    await page.close()
    await context.close()


# === E2E Screenshot Utilities ===

class ScenarioScreenshots:
    """Хелпер для сохранения скриншотов в сценарных тестах"""
    
    def __init__(self, test_name: str, screenshots_dir: Path):
        self.test_name = test_name
        self.screenshots_dir = screenshots_dir
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.counter = 0
    
    async def capture(self, name: str, page):
        """Сохраняет скриншот с именем"""
        self.counter += 1
        filename = f"{self.test_name}_{self.counter:02d}_{name}.png"
        filepath = self.screenshots_dir / filename
        try:
            await page.screenshot(path=str(filepath))
        except Exception:
            pass


@pytest_asyncio.fixture
async def scenario_screenshots(request):
    """Фикстура для сохранения скриншотов в сценарных тестах"""
    test_name = request.node.name.replace("/", "_").replace("::", "_")
    screenshots_dir = Path(__file__).parent / "frontend" / "browser" / "screenshots" / "scenarios"
    return ScenarioScreenshots(test_name, screenshots_dir)


DOCS_DIR = Path(__file__).parent.parent / "docs" / "user_docs" / "user_scenarios"


class ScenarioDocGenerator:
    """Генератор пользовательской документации из browser тестов."""
    
    def __init__(self, scenario_name: str, title: str):
        self.scenario_name = scenario_name
        self.title = title
        self.output_dir = DOCS_DIR / scenario_name
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.steps: list[dict] = []
        self.counter = 0
    
    async def step(self, page, title: str, description: str, selector: str = None):
        """Записывает шаг сценария."""
        self.counter += 1
        screenshot_name = f"{self.counter:02d}.png"
        screenshot_path = self.output_dir / screenshot_name
        
        if selector:
            await self._highlight_element(page, selector)
        
        await page.screenshot(path=str(screenshot_path))
        
        if selector:
            await self._remove_highlight(page, selector)
        
        self.steps.append({
            "number": self.counter,
            "title": title,
            "description": description,
            "screenshot": screenshot_name,
        })
    
    async def click(self, page, selector: str, title: str, description: str):
        """Подсвечивает элемент, делает скриншот, затем кликает."""
        await self.step(page, title, description, selector)
        await page.click(selector)
    
    async def fill(self, page, selector: str, value: str, title: str, description: str):
        """Подсвечивает поле ввода, делает скриншот, затем заполняет."""
        await self.step(page, title, description, selector)
        await page.fill(selector, value)
    
    async def _highlight_element(self, page, selector: str):
        """Добавляет красную рамку на элемент"""
        try:
            locator = page.locator(selector).first
            if await locator.count() > 0:
                await locator.evaluate("""
                    (el) => {
                        el.dataset.originalOutline = el.style.outline;
                        el.dataset.originalBoxShadow = el.style.boxShadow;
                        el.style.outline = '3px solid #ff0000';
                        el.style.boxShadow = '0 0 15px 5px rgba(255, 0, 0, 0.5)';
                    }
                """)
            await page.wait_for_timeout(100)
        except Exception:
            pass
    
    async def _remove_highlight(self, page, selector: str):
        """Убирает подсветку с элемента"""
        try:
            locator = page.locator(selector).first
            if await locator.count() > 0:
                await locator.evaluate("""
                    (el) => {
                        el.style.outline = el.dataset.originalOutline || '';
                        el.style.boxShadow = el.dataset.originalBoxShadow || '';
                        delete el.dataset.originalOutline;
                        delete el.dataset.originalBoxShadow;
                    }
                """)
        except Exception:
            pass
    
    def generate_markdown(self) -> str:
        """Генерирует markdown документацию"""
        lines = [f"# {self.title}", ""]
        
        for step in self.steps:
            lines.extend([
                f"## {step['number']}. {step['title']}",
                "",
                step['description'],
                "",
                f"![{step['title']}]({step['screenshot']})",
                "",
            ])
        
        return "\n".join(lines)
    
    def save(self):
        """Сохраняет index.md файл с документацией"""
        markdown = self.generate_markdown()
        index_path = self.output_dir / "index.md"
        index_path.write_text(markdown, encoding="utf-8")
        return index_path


@pytest_asyncio.fixture
async def doc_generator():
    """Фабрика для создания генератора документации."""
    generators = []
    
    def create(scenario_name: str, title: str) -> ScenarioDocGenerator:
        gen = ScenarioDocGenerator(scenario_name, title)
        generators.append(gen)
        return gen
    
    yield create
    
    for gen in generators:
        gen.save()


@pytest_asyncio.fixture
async def screenshot_on_failure(request, page):
    """Делает скриншот при падении теста"""
    yield
    
    if hasattr(request.node, "rep_call") and request.node.rep_call.failed:
        screenshot_dir = Path(__file__).parent / "frontend" / "browser" / "screenshots"
        screenshot_dir.mkdir(exist_ok=True)
        
        test_name = request.node.name.replace("/", "_").replace("::", "_")
        screenshot_path = screenshot_dir / f"{test_name}.png"
        await page.screenshot(path=str(screenshot_path))
        print(f"Screenshot saved: {screenshot_path}")
