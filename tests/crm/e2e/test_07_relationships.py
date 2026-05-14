"""
Тесты связей между entities.

User Story: Управление связями между entities для понимания контекста.
"""

import pytest


class TestRelationships:
    """Связи между entities"""

    @pytest.mark.asyncio
    async def test_create_relationship(self, crm_client, unique_id, auth_headers_system):
        """Создание связи вручную"""
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note {unique_id}"
        }, headers=auth_headers_system)
        note_id = note_resp.json()["entity_id"]

        contact_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Contact {unique_id}"
        }, headers=auth_headers_system)
        contact_id = contact_resp.json()["entity_id"]

        rel_resp = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": note_id,
            "target_entity_id": contact_id,
            "relationship_type": "mentions"
        }, headers=auth_headers_system)
        assert rel_resp.status_code == 200

        relationship = rel_resp.json()
        assert relationship["source_entity_id"] == note_id
        assert relationship["target_entity_id"] == contact_id
        assert relationship["relationship_type"] == "mentions"
        assert relationship["confidence"] == 1.0

    @pytest.mark.asyncio
    async def test_get_entity_relationships(self, crm_client, unique_id, auth_headers_system):
        """Получение всех связей entity"""
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note", "name": f"Note {unique_id}"
        }, headers=auth_headers_system)
        note_id = note_resp.json()["entity_id"]

        contact1_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact", "name": f"C1 {unique_id}"
        }, headers=auth_headers_system)
        contact1_id = contact1_resp.json()["entity_id"]

        contact2_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact", "name": f"C2 {unique_id}"
        }, headers=auth_headers_system)
        contact2_id = contact2_resp.json()["entity_id"]

        await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": note_id,
            "target_entity_id": contact1_id,
            "relationship_type": "mentions"
        }, headers=auth_headers_system)
        await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": note_id,
            "target_entity_id": contact2_id,
            "relationship_type": "mentions"
        }, headers=auth_headers_system)

        rels_resp = await crm_client.get(f"/crm/api/v1/entities/{note_id}/relationships", headers=auth_headers_system)
        assert rels_resp.status_code == 200

        data = rels_resp.json()
        assert len(data["relationships"]) >= 2

    @pytest.mark.asyncio
    async def test_bidirectional_relationships(self, crm_client, unique_id, auth_headers_system):
        """Двунаправленные связи (manages ↔ reports_to)"""
        manager_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact", "name": f"Manager {unique_id}"
        }, headers=auth_headers_system)
        manager_id = manager_resp.json()["entity_id"]

        employee_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact", "name": f"Employee {unique_id}"
        }, headers=auth_headers_system)
        employee_id = employee_resp.json()["entity_id"]

        rel1_resp = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": manager_id,
            "target_entity_id": employee_id,
            "relationship_type": "parent_of"
        }, headers=auth_headers_system)
        assert rel1_resp.status_code == 200

        rel2_resp = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": employee_id,
            "target_entity_id": manager_id,
            "relationship_type": "child_of"
        }, headers=auth_headers_system)
        assert rel2_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_custom_relationship_type(self, crm_client, unique_id, auth_headers_system):
        """Создание и использование кастомного типа связи"""
        type_resp = await crm_client.post("/crm/api/v1/relationships/types/", json={
            "type_id": f"works_for_{unique_id}",
            "name": "Работает в",
            "prompt": "Ищи где человек работает",
            "is_directed": True
        }, headers=auth_headers_system)
        assert type_resp.status_code == 200

        person_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact", "name": f"Person {unique_id}"
        }, headers=auth_headers_system)
        person_id = person_resp.json()["entity_id"]

        company_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "organization", "name": f"Company {unique_id}"
        }, headers=auth_headers_system)
        company_id = company_resp.json()["entity_id"]

        rel_resp = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": person_id,
            "target_entity_id": company_id,
            "relationship_type": f"works_for_{unique_id}"
        }, headers=auth_headers_system)
        assert rel_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_relationship_with_attributes(self, crm_client, unique_id, auth_headers_system):
        """Связь с дополнительными атрибутами"""
        entity1_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact", "name": f"E1 {unique_id}"
        }, headers=auth_headers_system)
        entity1_id = entity1_resp.json()["entity_id"]

        entity2_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "project", "name": f"Project {unique_id}"
        }, headers=auth_headers_system)
        entity2_id = entity2_resp.json()["entity_id"]

        rel_resp = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": entity1_id,
            "target_entity_id": entity2_id,
            "relationship_type": "assigned_to",
            "weight": 0.8,
            "confidence": 0.72,
            "attributes": {"role": "developer", "since": "2024-01-01"}
        }, headers=auth_headers_system)
        assert rel_resp.status_code == 200

        relationship = rel_resp.json()
        assert relationship["weight"] == 0.8
        assert relationship["confidence"] == 0.72
        assert relationship["attributes"]["role"] == "developer"

    @pytest.mark.asyncio
    async def test_delete_relationship(self, crm_client, unique_id, auth_headers_system):
        """Удаление связи"""
        entity1_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact", "name": f"E1 {unique_id}"
        }, headers=auth_headers_system)
        entity1_id = entity1_resp.json()["entity_id"]

        entity2_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact", "name": f"E2 {unique_id}"
        }, headers=auth_headers_system)
        entity2_id = entity2_resp.json()["entity_id"]

        rel_resp = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": entity1_id,
            "target_entity_id": entity2_id,
            "relationship_type": "mentions"
        }, headers=auth_headers_system)
        relationship_id = rel_resp.json()["relationship_id"]

        delete_resp = await crm_client.delete(f"/crm/api/v1/relationships/{relationship_id}", headers=auth_headers_system)
        assert delete_resp.status_code == 200

        get_resp = await crm_client.get(f"/crm/api/v1/relationships/{relationship_id}", headers=auth_headers_system)
        assert get_resp.status_code == 404

