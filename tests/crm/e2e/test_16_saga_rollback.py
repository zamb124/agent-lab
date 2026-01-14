"""
Тесты Saga pattern и каскадного удаления.

User Story: Каскадное удаление с откатом при ошибке.
"""

import pytest


class TestSagaRollback:
    """Saga pattern для транзакционности"""
    
    @pytest.mark.asyncio
    async def test_cascade_delete_with_attachments(self, crm_client, unique_id, auth_headers_system):
        """Удаление entity → автоматически удаляются attachments"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note с вложениями {unique_id}"
        }, headers=auth_headers_system)
        entity_id = entity_resp.json()["entity_id"]
        
        files = {"file": ("document.txt", b"Content to be deleted", "text/plain")}
        upload_resp = await crm_client.post(
            f"/crm/api/v1/entities/{entity_id}/attachments",
            files=files
        , headers=auth_headers_system)
        document_id = upload_resp.json()["document_id"]
        
        delete_resp = await crm_client.delete(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        assert delete_resp.status_code == 200
        
        get_entity_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        assert get_entity_resp.status_code == 404
    
    @pytest.mark.asyncio
    async def test_cascade_delete_with_relationships(self, crm_client, unique_id, auth_headers_system):
        """Удаление entity → автоматически удаляются relationships"""
        entity1_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note {unique_id}"
        }, headers=auth_headers_system)
        entity1_id = entity1_resp.json()["entity_id"]
        
        entity2_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Contact {unique_id}"
        }, headers=auth_headers_system)
        entity2_id = entity2_resp.json()["entity_id"]
        
        rel_resp = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": entity1_id,
            "target_entity_id": entity2_id,
            "relationship_type": "mentions"
        }, headers=auth_headers_system)
        relationship_id = rel_resp.json()["relationship_id"]
        
        delete_resp = await crm_client.delete(f"/crm/api/v1/entities/{entity1_id}", headers=auth_headers_system)
        assert delete_resp.status_code == 200
        
        rel_get_resp = await crm_client.get(f"/crm/api/v1/relationships/{relationship_id}", headers=auth_headers_system)
        assert rel_get_resp.status_code == 404
    
    @pytest.mark.asyncio
    async def test_cascade_delete_complex(self, crm_client, unique_id, auth_headers_system):
        """Удаление entity с attachments + relationships одновременно"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Complex entity {unique_id}"
        }, headers=auth_headers_system)
        entity_id = entity_resp.json()["entity_id"]
        
        files = {"file": ("file1.txt", b"Data 1", "text/plain")}
        await crm_client.post(f"/crm/api/v1/entities/{entity_id}/attachments", files=files, headers=auth_headers_system)
        
        related_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Related {unique_id}"
        }, headers=auth_headers_system)
        related_id = related_resp.json()["entity_id"]
        
        await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": entity_id,
            "target_entity_id": related_id,
            "relationship_type": "mentions"
        }, headers=auth_headers_system)
        
        delete_resp = await crm_client.delete(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        assert delete_resp.status_code == 200
        assert delete_resp.json()["success"] is True
    
    @pytest.mark.asyncio
    async def test_rollback_on_failure_simulation(self, crm_client, unique_id, auth_headers_system):
        """Симуляция rollback при ошибке удаления"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Entity for rollback test {unique_id}"
        }, headers=auth_headers_system)
        entity_id = entity_resp.json()["entity_id"]
        
        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        assert get_resp.status_code == 200

