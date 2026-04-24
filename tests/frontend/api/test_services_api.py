"""
Integration тесты для API проверки статуса сервисов.

Тесты БЕЗ моков - проверяем реальные HTTP запросы.
Проверяем мониторинг статуса микросервисов.
"""

import pytest
from httpx import AsyncClient

EXPECTED_SERVICES = {"flows", "crm", "rag", "sync", "office", "provider_litserve"}


@pytest.mark.asyncio
@pytest.mark.timeout(180)
class TestServicesAPI:
    """Тесты для API проверки статуса сервисов"""

    async def test_get_services_status_success(
        self,
        frontend_client: AsyncClient,
        frontend_container,
    ):
        """Получение статуса всех сервисов"""
        response = await frontend_client.get("/frontend/api/services/status")

        assert response.status_code == 200
        statuses = response.json()["items"]

        assert isinstance(statuses, list)

        service_names = {s["name"] for s in statuses}
        assert service_names == EXPECTED_SERVICES

        for service in statuses:
            assert "name" in service
            assert "status" in service
            assert "url" in service
            assert service["status"] in ["healthy", "unhealthy"]

            if service["status"] == "healthy":
                assert "response_time" in service

    async def test_services_status_no_auth_required(self, frontend_client: AsyncClient):
        """Статус сервисов доступен без авторизации"""
        response = await frontend_client.get("/frontend/api/services/status")

        assert response.status_code == 200

    async def test_services_status_response_time(
        self,
        frontend_client: AsyncClient,
    ):
        """Проверка что response_time корректный"""
        response = await frontend_client.get("/frontend/api/services/status")

        assert response.status_code == 200
        statuses = response.json()["items"]

        for service in statuses:
            if service["status"] == "healthy" and service["response_time"] is not None:
                assert service["response_time"] > 0
                assert service["response_time"] < 5000

    async def test_services_status_url_format(
        self,
        frontend_client: AsyncClient,
    ):
        """Проверка формата URL сервисов"""
        response = await frontend_client.get("/frontend/api/services/status")

        assert response.status_code == 200
        statuses = response.json()["items"]

        for service in statuses:
            assert service["url"].startswith("/")

    async def test_services_status_caching(
        self,
        frontend_client: AsyncClient,
    ):
        """Проверка что статус можно запрашивать многократно"""
        responses = []
        for _ in range(3):
            response = await frontend_client.get("/frontend/api/services/status")
            assert response.status_code == 200
            responses.append(response.json()["items"])

        for resp in responses:
            assert len(resp) > 0
            service_names = {s["name"] for s in resp}
            assert service_names == EXPECTED_SERVICES

    async def test_services_status_handles_unavailable_services(
        self,
        frontend_client: AsyncClient,
    ):
        """Проверка что API корректно обрабатывает недоступные сервисы"""
        response = await frontend_client.get("/frontend/api/services/status")

        assert response.status_code == 200
        statuses = response.json()["items"]

        assert len(statuses) == len(EXPECTED_SERVICES)

        unhealthy_services = [s for s in statuses if s["status"] == "unhealthy"]
        for service in unhealthy_services:
            assert service["response_time"] is None
            assert service["url"]

    async def test_services_status_json_format(
        self,
        frontend_client: AsyncClient,
    ):
        """Проверка формата JSON ответа"""
        response = await frontend_client.get("/frontend/api/services/status")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        statuses = response.json()["items"]
        assert isinstance(statuses, list)

    async def test_services_status_all_services_listed(
        self,
        frontend_client: AsyncClient,
    ):
        """Проверка что все ожидаемые сервисы в списке"""
        response = await frontend_client.get("/frontend/api/services/status")

        assert response.status_code == 200
        statuses = response.json()["items"]

        services_dict = {s["name"]: s for s in statuses}
        for name in EXPECTED_SERVICES:
            assert name in services_dict

        assert services_dict["flows"]["url"] == "/flows"
        assert services_dict["crm"]["url"] == "/crm"
        assert services_dict["rag"]["url"] == "/rag"
        assert services_dict["sync"]["url"] == "/sync"
        assert services_dict["office"]["url"] == "/office"
        assert services_dict["provider_litserve"]["url"] == "/litserve"

    async def test_services_status_consistent_across_requests(
        self,
        frontend_client: AsyncClient,
    ):
        """Проверка консистентности статусов при последовательных запросах"""
        response1 = await frontend_client.get("/frontend/api/services/status")
        response2 = await frontend_client.get("/frontend/api/services/status")

        assert response1.status_code == 200
        assert response2.status_code == 200

        statuses1 = {s["name"]: s["status"] for s in response1.json()["items"]}
        statuses2 = {s["name"]: s["status"] for s in response2.json()["items"]}

        assert set(statuses1.keys()) == set(statuses2.keys())
        assert len(statuses1) == len(statuses2)
