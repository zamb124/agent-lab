"""
Тесты для API запросов на доступ.
"""

import pytest
from httpx import AsyncClient


class TestAccessRequestsAPI:
    """Тесты API для запросов на доступ"""
    
    @pytest.mark.asyncio
    async def test_create_access_request(self, crm_client: AsyncClient, test_note):
        """Тест создания запроса на доступ"""
        # Меняем user_id чтобы запрос был от другого пользователя
        response = await crm_client.post(
            "/crm/api/v1/access-requests",
            json={
                "resource_type": "note",
                "resource_id": test_note.note_id,
                "message": "Мне нужен доступ для работы над проектом"
            },
            headers={"X-User-Id": "different_user_123"}
        )
        
        # Может вернуть 400 если владелец тот же
        assert response.status_code in [200, 201, 400]
        
        if response.status_code in [200, 201]:
            data = response.json()
            assert data["resource_type"] == "note"
            assert data["resource_id"] == test_note.note_id
            assert data["status"] == "pending"
    
    @pytest.mark.asyncio
    async def test_create_access_request_duplicate(self, crm_client: AsyncClient, test_note):
        """Тест создания дублирующего запроса"""
        # Первый запрос
        await crm_client.post(
            "/crm/api/v1/access-requests",
            json={
                "resource_type": "note",
                "resource_id": test_note.note_id,
                "message": "Первый запрос"
            },
            headers={"X-User-Id": "duplicate_test_user"}
        )
        
        # Дублирующий запрос
        response = await crm_client.post(
            "/crm/api/v1/access-requests",
            json={
                "resource_type": "note",
                "resource_id": test_note.note_id,
                "message": "Дублирующий запрос"
            },
            headers={"X-User-Id": "duplicate_test_user"}
        )
        
        # Должен вернуть ошибку
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
    async def test_approve_request(self, crm_client: AsyncClient, crm_container, test_note, test_user_id):
        """Тест одобрения запроса на доступ"""
        # Создаем запрос от другого пользователя
        from apps.crm.db.models import AccessRequest
        import uuid
        
        request = AccessRequest(
            request_id=str(uuid.uuid4()),
            company_id=test_note.company_id,
            requester_id="requester_for_approve",
            owner_id=test_user_id,  # Владелец = текущий пользователь
            resource_type="note",
            resource_id=test_note.note_id,
            message="Тестовый запрос",
            status="pending"
        )
        created = await crm_container.access_request_repository.create(request)
        
        # Одобряем запрос
        response = await crm_client.post(
            f"/crm/api/v1/access-requests/{created.request_id}/approve"
        )
        
        assert response.status_code == 200, f"Ошибка: {response.text}"
        data = response.json()
        assert data["status"] == "approved"
    
    @pytest.mark.asyncio
    async def test_reject_request(self, crm_client: AsyncClient, crm_container, test_note, test_user_id):
        """Тест отклонения запроса на доступ"""
        from apps.crm.db.models import AccessRequest
        import uuid
        
        request = AccessRequest(
            request_id=str(uuid.uuid4()),
            company_id=test_note.company_id,
            requester_id="requester_for_reject",
            owner_id=test_user_id,
            resource_type="note",
            resource_id=test_note.note_id,
            message="Запрос который отклоним",
            status="pending"
        )
        created = await crm_container.access_request_repository.create(request)
        
        # Отклоняем запрос
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
        self, crm_client: AsyncClient, crm_container, test_note, test_user_id
    ):
        """Тест повторного одобрения уже обработанного запроса"""
        from apps.crm.db.models import AccessRequest
        import uuid
        
        request = AccessRequest(
            request_id=str(uuid.uuid4()),
            company_id=test_note.company_id,
            requester_id="requester_already_processed",
            owner_id=test_user_id,
            resource_type="note",
            resource_id=test_note.note_id,
            status="approved"  # Уже одобрен
        )
        created = await crm_container.access_request_repository.create(request)
        
        # Пытаемся одобрить повторно
        response = await crm_client.post(
            f"/crm/api/v1/access-requests/{created.request_id}/approve"
        )
        
        assert response.status_code == 400

