"""
Простая конфигурация для pytest.
"""
import pytest
import pytest_asyncio
import asyncio
import os
import sys
import re
from pathlib import Path
from typing import Callable, Dict, Any, Optional
from unittest.mock import MagicMock

# Загружаем .env файл для тестов
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)
    print(f"✅ Загружен .env файл: {env_file}")
else:
    print(f"❌ .env файл не найден: {env_file}")

# Настройка переменных окружения для тестов
os.environ["DATABASE__URL"] = "postgresql+asyncpg://agent_user:agent_password@localhost:5432/agent_platform"
os.environ["DATABASE__CHECKPOINTER_URL"] = "postgresql://agent_user:agent_password@localhost:5432/agent_platform"
os.environ["SERVER__DEBUG"] = "true"
# Используем mock LLM по умолчанию для всех тестов
os.environ["LLM__DEFAULT_PROVIDER"] = "mock"
# Настройка S3 для тестов с реальными кредами Yandex
os.environ["S3__ENABLED"] = "true"
os.environ["S3__DEFAULT_BUCKET"] = "vkbucket"


@pytest.fixture(autouse=True, scope="function")
def cleanup_async_resources():
    """Очистка async ресурсов между тестами"""
    yield

    # Принудительная очистка после каждого теста
    try:
        import asyncio
        import gc

        # Получаем текущий loop
        try:
            loop = asyncio.get_running_loop()
            # Отменяем все pending tasks
            pending = asyncio.all_tasks(loop)
            for task in pending:
                if not task.done():
                    task.cancel()
        except RuntimeError:
            # Нет running loop
            pass

        # Принудительный garbage collection
        gc.collect()

        # Очистка SQLAlchemy connections
        try:
            from app.db.database import engine
            if hasattr(engine, 'pool'):
                engine.pool.dispose()
        except Exception:
            pass


    except Exception as e:
        print(f"⚠️ Ошибка очистки ресурсов: {e}")




@pytest.fixture
async def client():
    """HTTP клиент для тестирования API"""
    import httpx
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        yield client


@pytest.fixture(scope="function", autouse=True)
def test_context():
    """Фикстура для создания тестового контекста с компанией и балансом"""
    from app.core.context import set_context, clear_context
    from app.identity.models import User, Company
    from app.models.context_models import Context
    
    test_company = Company(
        company_id="test_company",
        subdomain="test",
        name="Test Company",
        tariff_plan="enterprise",
        balance=100000.0,
        monthly_budget=50000.0,
        current_month_spent=0.0,
        status="active"
    )
    
    test_user = User(
        user_id="test_user",
        provider="yandex",
        provider_user_id="test_123",
        email="test@example.com",
        name="Test User",
        status="active",
        groups=["user"],
        companies={"test_company": ["admin"]},
        active_company_id="test_company"
    )
    
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


@pytest_asyncio.fixture(scope="function")
async def save_test_company():
    """Сохраняет тестовую компанию в БД"""
    from app.core.storage import Storage
    from app.identity.models import Company
    
    storage = Storage()
    test_company = Company(
        company_id="test_company",
        subdomain="test",
        name="Test Company",
        tariff_plan="enterprise",
        balance=100000.0,
        monthly_budget=50000.0,
        current_month_spent=0.0,
        status="active"
    )
    
    await storage.set(f"company:{test_company.company_id}", test_company.model_dump_json(), force_global=True)
    await storage.set(f"subdomain:{test_company.subdomain}", f'"{test_company.company_id}"', force_global=True)
    
    yield test_company


# Переопределяем LLM конфиги агентов на mock для всех тестов (один раз при импорте)
import app.agents.weather.agent as _weather_module
_weather_module.WeatherAgent.llm_config = {"provider": "mock", "model": "mock-gpt-4", "temperature": 0.3}
_weather_module.TravelInfoAgent.llm_config = {"provider": "mock", "model": "mock-gpt-4", "temperature": 0.3}




# ==================== MOCK SERVER ДЛЯ ТЕСТИРОВАНИЯ ====================


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
    Mock HTTP сервер в стиле FastAPI с декораторами для регистрации эндпоинтов

    Использование:
        server = MockServer()

        @server.get("/api/v1/users")
        async def get_users(url: str, params: dict, **kwargs):
            return MockResponse(200, {"users": [...]})

        @server.get("/api/v1/users/{user_id}")
        async def get_user(url: str, params: dict, path_params: dict, **kwargs):
            user_id = int(path_params["user_id"])
            return MockResponse(200, {"id": user_id, "name": "Test"})
    """

    def __init__(self):
        self.routes: Dict[tuple, Callable] = {}
        self.requests = []

    def get(self, path_pattern: str):
        """Декоратор для регистрации GET эндпоинта"""
        def decorator(func: Callable):
            self.routes[("GET", path_pattern)] = func
            return func
        return decorator

    def post(self, path_pattern: str):
        """Декоратор для регистрации POST эндпоинта"""
        def decorator(func: Callable):
            self.routes[("POST", path_pattern)] = func
            return func
        return decorator

    def put(self, path_pattern: str):
        """Декоратор для регистрации PUT эндпоинта"""
        def decorator(func: Callable):
            self.routes[("PUT", path_pattern)] = func
            return func
        return decorator

    def delete(self, path_pattern: str):
        """Декоратор для регистрации DELETE эндпоинта"""
        def decorator(func: Callable):
            self.routes[("DELETE", path_pattern)] = func
            return func
        return decorator

    def _match_route(self, method: str, url: str) -> Optional[tuple]:
        """Находит подходящий роут и извлекает параметры из URL"""
        # Извлекаем путь из полного URL (убираем домен)
        # https://example.com/api/v1/users -> /api/v1/users
        from urllib.parse import urlparse
        path = urlparse(url).path

        for (route_method, pattern), handler in self.routes.items():
            if route_method != method:
                continue

            # Преобразуем FastAPI-like паттерн в regex
            # /api/v1/users/{user_id} -> /api/v1/users/(?P<user_id>[^/]+)
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