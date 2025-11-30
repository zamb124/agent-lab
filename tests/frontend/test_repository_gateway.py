"""
Тест Repository Gateway - frontend берет данные из agents через HTTP.

Проверяем что:
1. Agents сервис запускается и отвечает
2. X-Company-Id изолирует данные по компаниям
3. Данные корректно передаются между сервисами через HTTP
"""

import pytest
import httpx

from apps.agents.models import FlowConfig


class TestRepositoryGateway:
    """Тесты межсервисного взаимодействия через Repository Gateway"""
    
    @pytest.mark.asyncio
    async def test_agents_service_is_running(self, agents_service):
        """Проверяем что agents сервис запущен и отвечает"""
        url = f"{agents_service['url']}/health"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_agents_crud_endpoint_exists(self, agents_service):
        """Проверяем что CRUD endpoint для flow существует"""
        url = f"{agents_service['url']}/agents/api/v1/flow"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
        
        # Должен быть 200 (список) - endpoint существует
        assert response.status_code == 200, f"CRUD endpoint не найден: {url}"
    
    @pytest.mark.asyncio
    async def test_x_company_header_changes_context(
        self, agents_service, test_company, company_repo
    ):
        """
        Проверяем что X-Company-Id меняет контекст.
        
        Создаем компанию и проверяем что при запросе с её ID
        возвращается пустой список flows (а не flows системной компании).
        """
        await company_repo.set(test_company)
        
        try:
            url = f"{agents_service['url']}/agents/api/v1/flow"
            
            # Запрос БЕЗ X-Company-Id - вернет flows системной компании
            async with httpx.AsyncClient() as client:
                response_system = await client.get(url)
            
            # Запрос С X-Company-Id - должен вернуть пустой список
            headers = {"X-Company-Id": test_company.company_id}
            async with httpx.AsyncClient() as client:
                response_test = await client.get(url, headers=headers)
            
            # Системная компания имеет мигрированные flows
            assert len(response_system.json()) > 0, "System company должна иметь flows"
            
            # Тестовая компания НЕ должна иметь flows
            assert len(response_test.json()) == 0, "Test company НЕ должна иметь flows"
            
        finally:
            await company_repo.delete(test_company.company_id)
    
    @pytest.mark.asyncio
    async def test_agents_crud_with_company_header(
        self, agents_service, test_company, flow_repo, unique_id, test_context, company_repo
    ):
        """
        Проверяем что agents сервис корректно работает с X-Company-Id.
        
        1. Сохраняем test_company в БД
        2. Создаем flow через репозиторий
        3. Запрашиваем flow через HTTP с X-Company-Id заголовком
        4. Проверяем что flow найден
        """
        await company_repo.set(test_company)
        
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
            headers = {"X-Company-Id": test_company.company_id}
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers)
            
            assert response.status_code == 200, f"Flow не найден: {response.text}"
            data = response.json()
            assert data["flow_id"] == flow_id
            assert data["name"] == "Gateway Test Flow"
            
        finally:
            await flow_repo.delete(flow_id)
            await company_repo.delete(test_company.company_id)
