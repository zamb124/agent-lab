"""
Единая конфигурация фикстур для pytest.
Все тесты используют фикстуры отсюда для унификации.
"""
import pytest
import pytest_asyncio
import os
import uuid
from pathlib import Path
from typing import Callable, Dict, Optional
from unittest.mock import MagicMock
from dotenv import load_dotenv

from app.core.storage import Storage
from app.core.migrator import Migrator
from app.core.agent_factory import AgentFactory
from app.core.flow_factory import FlowFactory
from app.core.tool_factory import ToolFactory
from app.core.llm_factory import get_llm
from app.core.context import set_context, clear_context
from app.identity.models import User, Company
from app.models.context_models import Context
from app.models import (
    AgentConfig, AgentType, CodeMode, FlowConfig,
    ToolReference, LLMConfig
)


env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)

os.environ.setdefault("DATABASE__URL", "postgresql+asyncpg://agent_user:agent_password@localhost:5432/agent_platform")
os.environ.setdefault("DATABASE__CHECKPOINTER_URL", "postgresql://agent_user:agent_password@localhost:5432/agent_platform")
os.environ.setdefault("SERVER__DEBUG", "true")
os.environ.setdefault("LLM__DEFAULT_MODEL", "mock-gpt-4")
os.environ.setdefault("LLM__OPENROUTER__ENABLED", "false")
os.environ.setdefault("S3__ENABLED", "true")
os.environ.setdefault("S3__DEFAULT_BUCKET", "vkbucket")


@pytest.fixture(scope="session", autouse=True)
def setup_mock_llm_configs():
    """Настройка mock LLM для всех агентов (один раз на всю сессию)"""
    from app.models.core_models import LLMConfig
    
    mock_llm_config = LLMConfig(model="mock-gpt-4", temperature=0.3)
    
    try:
        import app.agents.weather.agent as weather_module
        weather_module.WeatherAgent.llm_config = mock_llm_config
        weather_module.TravelInfoAgent.llm_config = mock_llm_config
    except ImportError:
        pass
    
    try:
        import app.agents.calculator.agent as calc_module
        calc_module.CalculatorAgent.llm_config = mock_llm_config
    except ImportError:
        pass
    
    try:
        import app.agents.explainer.agent as explainer_module
        explainer_module.ExplainerAgent.llm_config = mock_llm_config
    except ImportError:
        pass
    
    try:
        import app.agents.router.agent as router_module
        router_module.RouterAgent.llm_config = mock_llm_config
    except ImportError:
        pass
    
    return mock_llm_config


@pytest_asyncio.fixture(scope="function")
async def migrated_db():
    """Миграция БД для каждого теста (для изоляции)
    
    Контекст НЕ устанавливается здесь - используется test_context с autouse=True
    """
    from app.db.database import engine
    
    migrator = Migrator()
    await migrator.run_full_migration()
    
    yield
    
    if hasattr(migrator, 'storage') and hasattr(migrator.storage, '_pool'):
        if migrator.storage._pool:
            await migrator.storage._pool.close()
    
    await engine.dispose()
    
    import gc
    gc.collect()


@pytest_asyncio.fixture
async def storage():
    """Чистый Storage для каждого теста"""
    from app.db.database import engine
    
    storage_instance = Storage()
    yield storage_instance
    
    if hasattr(storage_instance, '_pool') and storage_instance._pool:
        await storage_instance._pool.close()
    
    await engine.dispose()
    
    import gc
    gc.collect()


@pytest_asyncio.fixture
async def agent_factory():
    """AgentFactory для каждого теста"""
    return AgentFactory()


@pytest_asyncio.fixture
async def flow_factory():
    """FlowFactory для каждого теста"""
    return FlowFactory()


@pytest_asyncio.fixture
async def tool_factory():
    """ToolFactory для каждого теста"""
    return ToolFactory()


@pytest_asyncio.fixture
async def migrator():
    """Migrator для каждого теста"""
    return Migrator()


@pytest.fixture
def test_company() -> Company:
    """Тестовая компания с достаточным балансом"""
    return Company(
        company_id="test_company",
        subdomain="test",
        name="Test Company",
        tariff_plan="enterprise",
        balance=100000.0,
        monthly_budget=50000.0,
        current_month_spent=0.0,
        status="active"
    )


@pytest.fixture
def test_user(test_company: Company) -> User:
    """Тестовый пользователь"""
    return User(
        user_id="test_user",
        provider="yandex",
        provider_user_id="test_123",
        email="test@example.com",
        name="Test User",
        status="active",
        groups=["user"],
        companies={test_company.company_id: ["admin"]},
        active_company_id=test_company.company_id
    )


@pytest.fixture(autouse=True)
def test_context(test_user: User, test_company: Company):
    """Тестовый контекст для каждого теста (автоматически)"""
    context = Context(
        user=test_user,
        session_id="test_session",
        platform="api",
        active_company=test_company,
        user_companies=[test_company],
        metadata={}
    )
    
    set_context(context)
    yield context
    clear_context()


@pytest_asyncio.fixture
async def save_test_company(storage: Storage, test_company: Company):
    """Сохраняет тестовую компанию в БД"""
    await storage.set(f"company:{test_company.company_id}", test_company.model_dump_json(), force_global=True)
    await storage.set(f"subdomain:{test_company.subdomain}", f'"{test_company.company_id}"', force_global=True)
    
    yield test_company
    
    try:
        await storage.delete(f"company:{test_company.company_id}")
        await storage.delete(f"subdomain:{test_company.subdomain}")
    except:
        pass


@pytest_asyncio.fixture
async def variables_service(migrated_db):
    """VariablesService для работы с переменными компании
    
    Контекст будет доступен через get_context() благодаря test_context с autouse=True
    Зависит от migrated_db для инициализации БД в правильном event loop
    """
    from app.services.variables_service import VariablesService
    return VariablesService()


@pytest.fixture
def unique_id():
    """Генератор уникальных ID для тестов"""
    def _generate(prefix: str = "test") -> str:
        return f"{prefix}_{uuid.uuid4().hex[:8]}"
    return _generate


@pytest.fixture
def mock_llm():
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


@pytest.fixture
def mock_server():
    """Mock HTTP сервер для тестов"""
    return MockServer()


class TestHelpers:
    """Вспомогательные функции для тестов"""
    
    @staticmethod
    async def create_simple_agent(
        storage: Storage,
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
            llm_config=LLMConfig(model="mock-gpt-4"),
            source="test"
        )
        
        await storage.set_agent_config(agent_config)
        return agent_config
    
    @staticmethod
    async def create_simple_flow(
        storage: Storage,
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
        
        await storage.set_flow_config(flow_config)
        return flow_config
    
    @staticmethod
    def create_inline_tool(
        tool_id: str,
        function_name: str,
        function_body: str,
        description: str = ""
    ) -> ToolReference:
        """Создать inline tool для тестов"""
        inline_code = f'''
from app.core.tool_decorator import tool

@tool
{function_body}
'''
        
        return ToolReference(
            tool_id=tool_id,
            code_mode=CodeMode.INLINE_CODE,
            inline_code=inline_code.strip(),
            description=description or f"Test tool: {tool_id}"
        )


@pytest.fixture
def test_helpers():
    """Вспомогательные функции для тестов"""
    return TestHelpers


@pytest_asyncio.fixture
async def payment_service():
    """PaymentService для тестов"""
    from app.services.payment_service import PaymentService
    return PaymentService()


@pytest_asyncio.fixture
async def billing_service():
    """BillingService для тестов"""
    from app.services.billing_service import BillingService
    return BillingService()


@pytest.fixture
def yoomoney_provider():
    """YooMoney провайдер для интеграционных тестов платежей"""
    from app.core.clients.payment_providers.yoomoney_provider import YooMoneyProvider, YooMoneyConfig
    
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
    from app.identity.auth_service import AuthService
    return AuthService()


@pytest.fixture
def mock_storage_cache():
    """Mock storage с in-memory кешем для тестов"""
    cache = {}
    
    async def mock_get(key, force_global=False):
        return cache.get(key)
    
    async def mock_set(key, value, ttl=None, force_global=False):
        cache[key] = value
        return True
    
    async def mock_delete(key, force_global=False):
        cache.pop(key, None)
        return True
    
    return {
        'cache': cache,
        'get': mock_get,
        'set': mock_set,
        'delete': mock_delete
    }


@pytest.fixture
def payment_service_with_mock():
    """PaymentService с мок storage для тестов"""
    from unittest.mock import AsyncMock
    from app.services.payment_service import PaymentService
    
    service = PaymentService()
    service.storage = AsyncMock()
    return service


@pytest.fixture
def mock_provider():
    """Mock провайдер платежей для тестов"""
    from unittest.mock import Mock, AsyncMock
    from app.core.clients.payment_providers.base_provider import (
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
