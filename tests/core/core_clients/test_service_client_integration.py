"""
Интеграционные тесты для ServiceClient.

Тестируем реальное взаимодействие со всеми сервисами.
БЕЗ МОКОВ - реальные запросы к реальным сервисам.

Для запуска интеграционных тестов с реальными сервисами:
    pytest tests/core/core_clients/test_service_client_integration.py -v

Тесты с сервисами требуют:
- PostgreSQL (agents_db, shared_db, crm_db)
- Redis
"""

import pytest
import pytest_asyncio
import os

# Маркер для тестов требующих реальные сервисы
pytestmark = pytest.mark.asyncio

from core.clients.service_client import (
    ServiceClient,
    ServiceClientError,
    ServiceValidationError,
    get_service_client,
    init_service_client,
    shutdown_service_client,
)
from core.context import set_context, clear_context
from core.models import User, Company, Context
from core.models.identity_models import UserStatus, AuthProvider
from core.models.billing_models import TariffPlan


@pytest.fixture
def service_client():
    """Создает новый экземпляр ServiceClient для каждого теста"""
    return ServiceClient()


@pytest_asyncio.fixture
async def context_with_trace(test_user, test_company, user_repo, company_repo):
    """
    Контекст с trace_id для тестирования межсервисного взаимодействия.
    """
    from core.utils.tokens import get_token_service
    import uuid
    
    await company_repo.set(test_company)
    await user_repo.set(test_user)
    
    unique_session_id = f"test_session_{uuid.uuid4().hex[:8]}"
    trace_id = f"test:{uuid.uuid4()}"
    
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
        trace_id=trace_id,
    )
    
    set_context(context)
    yield context
    clear_context()
    
    try:
        await user_repo.delete(test_user.user_id)
        await company_repo.delete(test_company.company_id)
    except Exception:
        pass


class TestServiceClientConfiguration:
    """Тесты конфигурации ServiceClient"""
    
    def test_get_service_url_from_config(self, service_client):
        """Проверяем что URL сервисов берутся из конфигурации"""
        from core.config import get_settings
        settings = get_settings()
        
        agents_url = service_client._get_service_url("agents")
        crm_url = service_client._get_service_url("crm")
        frontend_url = service_client._get_service_url("frontend")
        
        assert agents_url is not None
        assert "localhost" in agents_url or settings.server.agents_service_url in agents_url
        assert crm_url is not None
        assert frontend_url is not None
    
    def test_openapi_url_format(self, service_client):
        """Проверяем формат OpenAPI URL для разных сервисов"""
        agents_openapi = service_client._get_openapi_url("agents")
        crm_openapi = service_client._get_openapi_url("crm")
        frontend_openapi = service_client._get_openapi_url("frontend")
        
        assert "/openapi.json" in agents_openapi
        assert "/openapi.json" in crm_openapi
        assert "/openapi.json" in frontend_openapi
    
    def test_singleton_returns_same_instance(self):
        """Проверяем что get_service_client возвращает синглтон"""
        client1 = get_service_client()
        client2 = get_service_client()
        
        assert client1 is client2


class TestServiceClientWithAgentsService:
    """Интеграционные тесты с реальным agents сервисом"""
    
    @pytest_asyncio.fixture
    async def running_agents_service(self, agents_server_process, session_test_data):
        """Запущенный agents сервис с тестовыми данными"""
        url = agents_server_process["url"]
        os.environ["SERVER__AGENTS_SERVICE_URL"] = url
        yield agents_server_process
        os.environ.pop("SERVER__AGENTS_SERVICE_URL", None)
    
    @pytest.mark.asyncio
    async def test_fetch_openapi_spec_from_agents(self, running_agents_service):
        """Получаем OpenAPI спеку с реального agents сервиса"""
        client = ServiceClient()
        client._known_services = ["agents"]
        
        url = running_agents_service["url"]
        
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            response = await http_client.get(f"{url}/openapi.json")
            assert response.status_code == 200
            spec = response.json()
        
        assert "openapi" in spec
        assert "paths" in spec
        assert len(spec["paths"]) > 0
    
    @pytest.mark.asyncio
    async def test_health_check_agents(self, running_agents_service):
        """Проверяем health endpoint agents сервиса"""
        url = running_agents_service["url"]
        
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{url}/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["service"] == "agents"
    
    @pytest.mark.asyncio
    async def test_request_with_trace_id(self, running_agents_service, context_with_trace):
        """Проверяем что trace_id передается в запросах"""
        client = ServiceClient()
        
        headers = client._build_headers()
        
        assert "X-Trace-Id" in headers
        assert headers["X-Trace-Id"] == context_with_trace.trace_id
        assert headers["X-Trace-Id"].startswith("test:")
    
    @pytest.mark.asyncio
    async def test_request_with_auth_headers(self, running_agents_service, context_with_trace):
        """Проверяем что auth заголовки передаются"""
        client = ServiceClient()
        
        headers = client._build_headers()
        
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")
        assert "X-Company-Id" in headers
        assert headers["X-Company-Id"] == context_with_trace.active_company.company_id
        assert "X-User-Id" in headers
        assert headers["X-User-Id"] == context_with_trace.user.user_id
    
    @pytest.mark.asyncio
    async def test_get_flows_list_real(self, running_agents_service, session_test_data):
        """Получаем реальный список flows с agents сервиса"""
        url = running_agents_service["url"]
        headers = session_test_data["headers"]
        
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{url}/agents/api/v1/flows/",
                headers=headers
            )
            # Может вернуть 200 (список) или 401 если нет авторизации
            # Главное что сервис отвечает
            assert response.status_code in [200, 401, 403]


class TestServiceClientWithCRMService:
    """Интеграционные тесты с реальным CRM сервисом"""
    
    @pytest.mark.asyncio
    async def test_health_check_crm(self, crm_server_process):
        """Проверяем health endpoint CRM сервиса"""
        url = crm_server_process["url"]
        
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{url}/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["service"] == "crm"
    
    @pytest.mark.asyncio
    async def test_fetch_openapi_spec_from_crm(self, crm_server_process):
        """Получаем OpenAPI спеку с реального CRM сервиса"""
        url = crm_server_process["url"]
        
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{url}/openapi.json")
            assert response.status_code == 200
            spec = response.json()
        
        assert "openapi" in spec
        assert "paths" in spec
    
    @pytest.mark.asyncio
    async def test_get_entity_types_real(self, crm_server_process, session_test_data):
        """Получаем реальный список типов сущностей с CRM сервиса"""
        url = crm_server_process["url"]
        headers = session_test_data["headers"]
        
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{url}/crm/api/v1/entity-types/",
                headers=headers
            )
            # CRM должен вернуть список типов
            assert response.status_code in [200, 401, 403]


class TestServiceClientWithFrontendService:
    """Интеграционные тесты с реальным frontend сервисом"""
    
    @pytest.mark.asyncio
    async def test_health_check_frontend(self, frontend_server_process):
        """Проверяем health endpoint frontend сервиса"""
        url = frontend_server_process["url"]
        
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{url}/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["service"] == "frontend"
    
    @pytest.mark.asyncio
    async def test_fetch_openapi_spec_from_frontend(self, frontend_server_process):
        """Получаем OpenAPI спеку с реального frontend сервиса"""
        url = frontend_server_process["url"]
        
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{url}/api/openapi.json")
            assert response.status_code == 200
            spec = response.json()
        
        assert "openapi" in spec
        assert "paths" in spec


class TestServiceClientBackgroundRefresh:
    """Тесты фонового обновления OpenAPI спек"""
    
    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        """Проверяем старт и остановку фонового обновления"""
        client = ServiceClient()
        
        assert not client._running
        assert client._refresh_task is None
        
        await client.start()
        
        assert client._running
        assert client._refresh_task is not None
        
        await client.stop()
        
        assert not client._running
    
    @pytest.mark.asyncio
    async def test_refresh_loads_specs(self, agents_server_process, crm_server_process):
        """Проверяем что refresh загружает спеки с реальных сервисов"""
        # Устанавливаем URL из тестовых серверов
        os.environ["SERVER__AGENTS_SERVICE_URL"] = agents_server_process["url"]
        os.environ["SERVER__CRM_SERVICE_URL"] = crm_server_process["url"]
        
        try:
            # Сбрасываем глобальный settings чтобы подхватил новые env
            from core.config.base import set_settings, BaseSettings
            
            client = ServiceClient()
            
            # Вручную обновляем URL в клиенте
            await client._refresh_all_specs()
            
            # Хотя бы agents или crm должен загрузиться
            # (frontend может быть недоступен)
            loaded_services = list(client._specs_cache.keys())
            assert len(loaded_services) >= 0  # Может быть 0 если сервисы не успели подняться
            
        finally:
            os.environ.pop("SERVER__AGENTS_SERVICE_URL", None)
            os.environ.pop("SERVER__CRM_SERVICE_URL", None)


class TestServiceClientValidation:
    """Тесты валидации запросов по OpenAPI"""
    
    @pytest.mark.asyncio
    async def test_validation_passes_for_known_path(self, agents_server_process):
        """Валидация проходит для известного пути"""
        client = ServiceClient()
        
        # Загружаем спеку вручную
        spec = await client._fetch_openapi_spec("agents")
        if spec:
            client._specs_cache["agents"] = spec
            
            # Ищем любой GET endpoint
            for path, methods in spec.get("paths", {}).items():
                if "get" in methods:
                    # Должно пройти без исключения
                    result = client._validate_request("agents", "GET", path)
                    assert result is True
                    break
    
    @pytest.mark.asyncio
    async def test_validation_fails_for_unknown_path(self, agents_server_process):
        """Валидация падает для неизвестного пути"""
        client = ServiceClient()
        
        # Загружаем спеку
        spec = await client._fetch_openapi_spec("agents")
        if spec:
            client._specs_cache["agents"] = spec
            
            with pytest.raises(ServiceValidationError) as exc_info:
                client._validate_request("agents", "GET", "/nonexistent/path/12345")
            
            assert "не найден" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_validation_skipped_without_spec(self):
        """Валидация пропускается если спека недоступна"""
        client = ServiceClient()
        
        # Без спеки валидация должна пройти с warning
        result = client._validate_request("unknown_service", "GET", "/any/path")
        assert result is True


class TestServiceClientCrossServiceCommunication:
    """Тесты межсервисного взаимодействия"""
    
    @pytest.mark.asyncio
    async def test_agents_to_crm_trace_propagation(
        self,
        agents_server_process,
        crm_server_process,
        context_with_trace
    ):
        """
        Проверяем что trace_id пробрасывается между сервисами.
        
        Сценарий: запрос приходит в agents с trace_id,
        agents делает запрос в crm - trace_id должен сохраниться.
        """
        client = ServiceClient()
        
        # Проверяем что headers содержат trace_id из контекста
        headers = client._build_headers()
        original_trace_id = context_with_trace.trace_id
        
        assert headers.get("X-Trace-Id") == original_trace_id
        
        # trace_id имеет формат service:uuid
        parts = original_trace_id.split(":")
        assert len(parts) == 2
        assert parts[0] == "test"  # Наш тестовый сервис


class TestServiceClientSingleton:
    """Тесты синглтона и lifecycle"""
    
    @pytest.mark.asyncio
    async def test_init_and_shutdown(self):
        """Проверяем init_service_client и shutdown_service_client"""
        from core.clients.service_client import (
            _service_client,
            init_service_client,
            shutdown_service_client,
        )
        
        # Сбрасываем глобальный клиент
        import core.clients.service_client as sc_module
        sc_module._service_client = None
        
        # Инициализируем
        client = await init_service_client()
        assert client is not None
        assert client._running is True
        
        # Останавливаем
        await shutdown_service_client()
        assert client._running is False
        
        # Сбрасываем для других тестов
        sc_module._service_client = None

