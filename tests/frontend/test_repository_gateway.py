"""
Тест Repository Gateway - frontend берет данные из agents через HTTP.

Проверяем что:
1. Agents сервис запускается и отвечает
2. X-Company-Id изолирует данные по компаниям
3. Данные корректно передаются между сервисами через HTTP
"""

import pytest
import pytest_asyncio
import httpx

from apps.agents.models import FlowConfig
from core.utils.tokens import get_token_service


class TestRepositoryGateway:
    """Тесты межсервисного взаимодействия через Repository Gateway"""
    
    @pytest_asyncio.fixture
    async def system_auth_headers(self, user_repo):
        """Заголовки авторизации для системной компании"""
        from core.models.identity_models import User, UserStatus, AuthProvider
        
        # Создаем системного пользователя
        system_user = User(
            user_id="system_test_user",
            provider=AuthProvider.YANDEX,
            provider_user_id="system_test",
            email="system@test.com",
            name="System Test User",
            status=UserStatus.ACTIVE,
            groups=["admin"],
            companies={"system": ["admin"]},
            active_company_id="system",
        )
        await user_repo.set(system_user)
        
        token_service = get_token_service()
        token = token_service.create_token(
            user_id="system_test_user",
            company_id="system",
            roles=["admin"],
        )
        
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Company-Id": "system",
        }
        
        yield headers
        
        # Очистка
        try:
            await user_repo.delete("system_test_user")
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_agents_service_is_running(self, agents_service):
        """Проверяем что agents сервис запущен и отвечает"""
        url = f"{agents_service['url']}/health"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_agents_crud_endpoint_exists(self, agents_service, system_auth_headers):
        """Проверяем что CRUD endpoint для flow существует"""
        url = f"{agents_service['url']}/agents/api/v1/flow"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=system_auth_headers)
        
        # Должен быть 200 (список) - endpoint существует
        assert response.status_code == 200, f"CRUD endpoint не найден: {url}"
    
    @pytest.mark.asyncio
    async def test_x_company_header_changes_context(
        self, agents_service, system_auth_headers, service_auth_headers
    ):
        """
        Проверяем что X-Company-Id меняет контекст.
        
        При запросе с системной компанией возвращаются flows.
        При запросе с тестовой компанией возвращается пустой список.
        
        service_auth_headers уже создает test_company и test_user в БД.
        """
        url = f"{agents_service['url']}/agents/api/v1/flow"
        
        # Запрос с системной компанией - вернет flows системной компании
        async with httpx.AsyncClient() as client:
            response_system = await client.get(url, headers=system_auth_headers)
        
        # Запрос с тестовой компанией - должен вернуть пустой список
        async with httpx.AsyncClient() as client:
            response_test = await client.get(url, headers=service_auth_headers)
        
        # Системная компания имеет мигрированные flows
        assert response_system.status_code == 200, f"System company request failed: {response_system.text}"
        assert len(response_system.json()) > 0, "System company должна иметь flows"
        
        # Тестовая компания НЕ должна иметь flows
        assert response_test.status_code == 200, f"Test company request failed: {response_test.text}"
        assert len(response_test.json()) == 0, "Test company НЕ должна иметь flows"
    
    @pytest.mark.asyncio
    async def test_agents_crud_with_company_header(
        self, agents_service, flow_repo, unique_id, test_context, service_auth_headers
    ):
        """
        Проверяем что agents сервис корректно работает с X-Company-Id.
        
        1. Создаем flow через репозиторий (test_context задает компанию)
        2. Запрашиваем flow через HTTP с X-Company-Id заголовком
        3. Проверяем что flow найден
        
        service_auth_headers уже создает test_company и test_user в БД.
        test_context устанавливает контекст для репозитория.
        """
        flow_id = unique_id("gateway_test_flow")
        flow = FlowConfig(
            flow_id=flow_id,
            name="Gateway Test Flow",
            description="Flow для теста Repository Gateway",
            entry_point_agent="test_agent",
            source="test"
        )
        await flow_repo.set(flow)
        
        try:
            url = f"{agents_service['url']}/agents/api/v1/flow/{flow_id}"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=service_auth_headers)
            
            assert response.status_code == 200, f"Flow не найден: {response.text}"
            data = response.json()
            assert data["flow_id"] == flow_id
            assert data["name"] == "Gateway Test Flow"
            
        finally:
            await flow_repo.delete(flow_id)
