"""
Integration тесты для API проверки статуса сервисов.

Тесты БЕЗ моков - проверяем реальные HTTP запросы.
Проверяем мониторинг статуса микросервисов.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
class TestServicesAPI:
    """Тесты для API проверки статуса сервисов"""

    async def test_get_services_status_success(
        self, 
        frontend_client: AsyncClient, 
        frontend_container
    ):
        """Получение статуса всех сервисов"""
        response = await frontend_client.get("/frontend/api/services/status")
        
        assert response.status_code == 200
        statuses = response.json()
        
        # Должен быть массив
        assert isinstance(statuses, list)
        
        # Проверяем что есть основные сервисы
        service_names = [s["name"] for s in statuses]
        assert "flows" in service_names
        assert "crm" in service_names
        assert "rag" in service_names
        
        # Проверяем структуру каждого сервиса
        for service in statuses:
            assert "name" in service
            assert "status" in service
            assert "url" in service
            assert service["status"] in ["healthy", "unhealthy"]
            
            # response_time может быть None для unhealthy
            if service["status"] == "healthy":
                assert "response_time" in service

    async def test_services_status_no_auth_required(self, frontend_client: AsyncClient):
        """Статус сервисов доступен без авторизации"""
        response = await frontend_client.get("/frontend/api/services/status")
        
        # Должен работать без авторизации для мониторинга
        assert response.status_code == 200

    async def test_services_status_response_time(
        self, 
        frontend_client: AsyncClient
    ):
        """Проверка что response_time корректный"""
        response = await frontend_client.get("/frontend/api/services/status")
        
        assert response.status_code == 200
        statuses = response.json()
        
        for service in statuses:
            if service["status"] == "healthy" and service["response_time"] is not None:
                # Response time должен быть положительным числом в миллисекундах
                assert service["response_time"] > 0
                # Обычно не должен превышать 5 секунд для health check
                assert service["response_time"] < 5000

    async def test_services_status_url_format(
        self, 
        frontend_client: AsyncClient
    ):
        """Проверка формата URL сервисов"""
        response = await frontend_client.get("/frontend/api/services/status")
        
        assert response.status_code == 200
        statuses = response.json()
        
        for service in statuses:
            # URL должен быть корректным
            assert service["url"].startswith("/")
            assert service["name"] in service["url"]

    async def test_services_status_caching(
        self, 
        frontend_client: AsyncClient
    ):
        """Проверка что статус можно запрашивать многократно"""
        # Делаем несколько запросов подряд
        responses = []
        for _ in range(3):
            response = await frontend_client.get("/frontend/api/services/status")
            assert response.status_code == 200
            responses.append(response.json())
        
        # Все ответы должны иметь одинаковую структуру
        for resp in responses:
            assert len(resp) > 0
            service_names = {s["name"] for s in resp}
            assert service_names == {"flows", "crm", "rag"}

    async def test_services_status_handles_unavailable_services(
        self, 
        frontend_client: AsyncClient
    ):
        """Проверка что API корректно обрабатывает недоступные сервисы"""
        response = await frontend_client.get("/frontend/api/services/status")
        
        assert response.status_code == 200
        statuses = response.json()
        
        # API должен вернуть статус для всех сервисов, даже если они недоступны
        assert len(statuses) >= 3
        
        # Могут быть unhealthy сервисы - это нормально
        unhealthy_services = [s for s in statuses if s["status"] == "unhealthy"]
        
        for service in unhealthy_services:
            # У недоступных сервисов response_time должен быть None
            assert service["response_time"] is None
            # Но URL должен быть указан
            assert service["url"]

    async def test_services_status_json_format(
        self, 
        frontend_client: AsyncClient
    ):
        """Проверка формата JSON ответа"""
        response = await frontend_client.get("/frontend/api/services/status")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        
        # Должен быть валидный JSON
        statuses = response.json()
        assert isinstance(statuses, list)

    async def test_services_status_all_services_listed(
        self, 
        frontend_client: AsyncClient
    ):
        """Проверка что все ожидаемые сервисы в списке"""
        response = await frontend_client.get("/frontend/api/services/status")
        
        assert response.status_code == 200
        statuses = response.json()
        
        # Создаем словарь для удобства
        services_dict = {s["name"]: s for s in statuses}
        
        # Проверяем что все ключевые сервисы присутствуют
        assert "flows" in services_dict
        assert "crm" in services_dict
        assert "rag" in services_dict
        
        # Проверяем URL сервисов
        assert services_dict["flows"]["url"] == "/flows"
        assert services_dict["crm"]["url"] == "/crm"
        assert services_dict["rag"]["url"] == "/rag"

    async def test_services_status_consistent_across_requests(
        self, 
        frontend_client: AsyncClient
    ):
        """Проверка консистентности статусов при последовательных запросах"""
        # Делаем два запроса
        response1 = await frontend_client.get("/frontend/api/services/status")
        response2 = await frontend_client.get("/frontend/api/services/status")
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        statuses1 = {s["name"]: s["status"] for s in response1.json()}
        statuses2 = {s["name"]: s["status"] for s in response2.json()}
        
        # Набор сервисов должен быть одинаковым
        assert set(statuses1.keys()) == set(statuses2.keys())
        
        # Статусы могут измениться, но сервисы должны остаться теми же
        assert len(statuses1) == len(statuses2)

