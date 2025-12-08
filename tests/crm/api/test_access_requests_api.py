"""
Тесты для API запросов на доступ.

Используют crm_client с test_context пользователем.
Для approve/reject тестов owner_id должен совпадать с crm_client.test_user.
"""

import pytest
import uuid
from httpx import AsyncClient

from apps.crm.db.models import AccessRequest


class TestAccessRequestsAPI:
    """Тесты API для запросов на доступ"""
    
    @pytest.mark.asyncio
    async def test_create_access_request(self, crm_client: AsyncClient, test_note):
        """Тест создания запроса на доступ"""
        response = await crm_client.post(
            "/crm/api/v1/access-requests",
            json={
                "resource_type": "note",
                "resource_id": test_note.note_id,
                "message": "Мне нужен доступ для работы над проектом"
            },
        )
        
        # 400 если владелец = текущий пользователь (нельзя запрашивать доступ к своим)
        assert response.status_code == 400
    
    @pytest.mark.asyncio
    async def test_get_incoming_requests(self, crm_client: AsyncClient):
        """Тест получения входящих запросов"""
        response = await crm_client.get("/crm/api/v1/access-requests/incoming")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_get_incoming_requests_with_status_filter(self, crm_client: AsyncClient):
        """Тест получения входящих запросов с фильтром по статусу"""
        response = await crm_client.get(
            "/crm/api/v1/access-requests/incoming",
            params={"status": "pending"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        for req in data:
            assert req["status"] == "pending"
    
    @pytest.mark.asyncio
    async def test_get_outgoing_requests(self, crm_client: AsyncClient):
        """Тест получения исходящих запросов"""
        response = await crm_client.get("/crm/api/v1/access-requests/outgoing")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_get_pending_count(self, crm_client: AsyncClient):
        """Тест получения количества ожидающих запросов"""
        response = await crm_client.get("/crm/api/v1/access-requests/pending-count")
        
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert isinstance(data["count"], int)
        assert data["count"] >= 0
    
    @pytest.mark.asyncio
    async def test_approve_request(self, crm_client: AsyncClient, crm_container, test_note):
        """Тест одобрения запроса на доступ"""
        # owner_id = текущий пользователь из crm_client
        owner_id = crm_client.test_user.user_id
        
        request = AccessRequest(
            request_id=str(uuid.uuid4()),
            company_id=test_note.company_id,
            requester_id="requester_for_approve",
            owner_id=owner_id,
            resource_type="note",
            resource_id=test_note.note_id,
            message="Тестовый запрос",
            status="pending"
        )
        created = await crm_container.access_request_repository.create(request)
        
        response = await crm_client.post(
            f"/crm/api/v1/access-requests/{created.request_id}/approve"
        )
        
        assert response.status_code == 200, f"Ошибка: {response.text}"
        data = response.json()
        assert data["status"] == "approved"
    
    @pytest.mark.asyncio
    async def test_reject_request(self, crm_client: AsyncClient, crm_container, test_note):
        """Тест отклонения запроса на доступ"""
        owner_id = crm_client.test_user.user_id
        
        request = AccessRequest(
            request_id=str(uuid.uuid4()),
            company_id=test_note.company_id,
            requester_id="requester_for_reject",
            owner_id=owner_id,
            resource_type="note",
            resource_id=test_note.note_id,
            message="Запрос который отклоним",
            status="pending"
        )
        created = await crm_container.access_request_repository.create(request)
        
        response = await crm_client.post(
            f"/crm/api/v1/access-requests/{created.request_id}/reject"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"
    
    @pytest.mark.asyncio
    async def test_approve_nonexistent_request(self, crm_client: AsyncClient):
        """Тест одобрения несуществующего запроса"""
        response = await crm_client.post(
            "/crm/api/v1/access-requests/nonexistent_id/approve"
        )
        
        assert response.status_code == 400
    
    @pytest.mark.asyncio
    async def test_approve_already_processed_request(
        self, crm_client: AsyncClient, crm_container, test_note
    ):
        """Тест повторного одобрения уже обработанного запроса"""
        owner_id = crm_client.test_user.user_id
        
        request = AccessRequest(
            request_id=str(uuid.uuid4()),
            company_id=test_note.company_id,
            requester_id="requester_already_processed",
            owner_id=owner_id,
            resource_type="note",
            resource_id=test_note.note_id,
            status="approved"
        )
        created = await crm_container.access_request_repository.create(request)
        
        response = await crm_client.post(
            f"/crm/api/v1/access-requests/{created.request_id}/approve"
        )
        
        assert response.status_code == 400

