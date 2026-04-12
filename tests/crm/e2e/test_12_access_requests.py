"""
Тесты запросов доступа к entities.

User Story: Запросы доступа к чужим/скрытым entities.
"""

import pytest


class TestAccessRequests:
    """Запросы доступа к entities"""
    
    @pytest.mark.asyncio
    async def test_request_access_to_entity(self, crm_client, unique_id, auth_headers_system):
        """Запрос доступа к скрытой entity"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Private note {unique_id}"
        }, headers=auth_headers_system)
        entity_id = entity_resp.json()["entity_id"]
        
        request_resp = await crm_client.post("/crm/api/v1/access-requests", json={
            "resource_type": "entity",
            "resource_id": entity_id,
            "message": f"Нужен доступ для работы над проектом {unique_id}"
        }, headers=auth_headers_system)
        assert request_resp.status_code == 200
        
        request = request_resp.json()
        assert request["status"] == "pending"
        assert request["resource_id"] == entity_id
    
    @pytest.mark.asyncio
    async def test_approve_access_request(self, crm_client, unique_id, auth_headers_system):
        """Владелец одобряет запрос доступа"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note {unique_id}"
        }, headers=auth_headers_system)
        entity_id = entity_resp.json()["entity_id"]
        
        request_resp = await crm_client.post("/crm/api/v1/access-requests", json={
            "resource_type": "entity",
            "resource_id": entity_id,
            "message": "Прошу доступ"
        }, headers=auth_headers_system)
        request_id = request_resp.json()["request_id"]
        
        approve_resp = await crm_client.put(f"/crm/api/v1/access-requests/{request_id}", json={
            "status": "approved"
        }, headers=auth_headers_system)
        assert approve_resp.status_code == 200
        
        get_resp = await crm_client.get(f"/crm/api/v1/access-requests/{request_id}", headers=auth_headers_system)
        request = get_resp.json()
        assert request["status"] == "approved"
    
    @pytest.mark.asyncio
    async def test_reject_access_request(self, crm_client, unique_id, auth_headers_system):
        """Владелец отклоняет запрос"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note {unique_id}"
        }, headers=auth_headers_system)
        entity_id = entity_resp.json()["entity_id"]
        
        request_resp = await crm_client.post("/crm/api/v1/access-requests", json={
            "resource_type": "entity",
            "resource_id": entity_id,
            "message": "Запрос"
        }, headers=auth_headers_system)
        request_id = request_resp.json()["request_id"]
        
        reject_resp = await crm_client.put(f"/crm/api/v1/access-requests/{request_id}", json={
            "status": "rejected"
        }, headers=auth_headers_system)
        assert reject_resp.status_code == 200
    
    @pytest.mark.asyncio
    async def test_list_pending_requests(self, crm_client, unique_id, auth_headers_system):
        """Список запросов на рассмотрении"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note {unique_id}"
        }, headers=auth_headers_system)
        entity_id = entity_resp.json()["entity_id"]
        
        await crm_client.post("/crm/api/v1/access-requests", json={
            "resource_type": "entity",
            "resource_id": entity_id,
            "message": f"Запрос {unique_id}"
        }, headers=auth_headers_system)
        
        list_resp = await crm_client.get("/crm/api/v1/access-requests?status=pending", headers=auth_headers_system)
        assert list_resp.status_code == 200
        
        requests = list_resp.json()["items"]
        pending = [r for r in requests if unique_id in r.get("message", "")]
        assert len(pending) >= 1

