"""
Тесты связей между entities.

User Story: Управление связями между entities для понимания контекста.
"""

from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_dict, object_list, object_str


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _entity_id(response: Response) -> str:
    return object_str(_http_json(response).get("entity_id"), field="entity_id")


def _relationship_id(response: Response) -> str:
    return object_str(_http_json(response).get("relationship_id"), field="relationship_id")


def _relationship_rows(response: Response) -> list[dict[str, object]]:
    return object_list(_http_json(response).get("relationships"))


def _json_float(payload: dict[str, object], key: str) -> float:
    value = payload[key]
    if not isinstance(value, (int, float)):
        raise AssertionError(f"{key} must be float")
    return float(value)


class TestRelationships:
    """Связи между entities"""

    @pytest.mark.asyncio
    async def test_create_relationship(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Создание связи вручную"""
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note {unique_id}",
        }, headers=auth_headers_system)
        note_id = _entity_id(note_resp)

        contact_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Contact {unique_id}",
        }, headers=auth_headers_system)
        contact_id = _entity_id(contact_resp)

        rel_resp = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": note_id,
            "target_entity_id": contact_id,
            "relationship_type": "mentions",
        }, headers=auth_headers_system)
        assert rel_resp.status_code == 200

        relationship = _http_json(rel_resp)
        assert object_str(relationship.get("source_entity_id"), field="source_entity_id") == note_id
        assert object_str(relationship.get("target_entity_id"), field="target_entity_id") == contact_id
        assert object_str(relationship.get("relationship_type"), field="relationship_type") == "mentions"
        assert _json_float(relationship, "confidence") == 1.0

    @pytest.mark.asyncio
    async def test_get_entity_relationships(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Получение всех связей entity"""
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note", "name": f"Note {unique_id}",
        }, headers=auth_headers_system)
        note_id = _entity_id(note_resp)

        contact1_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact", "name": f"C1 {unique_id}",
        }, headers=auth_headers_system)
        contact1_id = _entity_id(contact1_resp)

        contact2_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact", "name": f"C2 {unique_id}",
        }, headers=auth_headers_system)
        contact2_id = _entity_id(contact2_resp)

        _ = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": note_id,
            "target_entity_id": contact1_id,
            "relationship_type": "mentions",
        }, headers=auth_headers_system)
        _ = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": note_id,
            "target_entity_id": contact2_id,
            "relationship_type": "mentions",
        }, headers=auth_headers_system)

        rels_resp = await crm_client.get(
            f"/crm/api/v1/entities/{note_id}/relationships",
            headers=auth_headers_system,
        )
        assert rels_resp.status_code == 200

        assert len(_relationship_rows(rels_resp)) >= 2

    @pytest.mark.asyncio
    async def test_bidirectional_relationships(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Двунаправленные связи (manages ↔ reports_to)"""
        manager_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact", "name": f"Manager {unique_id}",
        }, headers=auth_headers_system)
        manager_id = _entity_id(manager_resp)

        employee_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact", "name": f"Employee {unique_id}",
        }, headers=auth_headers_system)
        employee_id = _entity_id(employee_resp)

        rel1_resp = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": manager_id,
            "target_entity_id": employee_id,
            "relationship_type": "parent_of",
        }, headers=auth_headers_system)
        assert rel1_resp.status_code == 200

        rel2_resp = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": employee_id,
            "target_entity_id": manager_id,
            "relationship_type": "child_of",
        }, headers=auth_headers_system)
        assert rel2_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_custom_relationship_type(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Создание и использование кастомного типа связи"""
        type_resp = await crm_client.post("/crm/api/v1/relationships/types/", json={
            "type_id": f"works_for_{unique_id}",
            "name": "Работает в",
            "prompt": "Ищи где человек работает",
            "is_directed": True,
        }, headers=auth_headers_system)
        assert type_resp.status_code == 200

        person_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact", "name": f"Person {unique_id}",
        }, headers=auth_headers_system)
        person_id = _entity_id(person_resp)

        company_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "organization", "name": f"Company {unique_id}",
        }, headers=auth_headers_system)
        company_id = _entity_id(company_resp)

        rel_resp = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": person_id,
            "target_entity_id": company_id,
            "relationship_type": f"works_for_{unique_id}",
        }, headers=auth_headers_system)
        assert rel_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_relationship_with_attributes(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Связь с дополнительными атрибутами"""
        entity1_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact", "name": f"E1 {unique_id}",
        }, headers=auth_headers_system)
        entity1_id = _entity_id(entity1_resp)

        entity2_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "project", "name": f"Project {unique_id}",
        }, headers=auth_headers_system)
        entity2_id = _entity_id(entity2_resp)

        rel_resp = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": entity1_id,
            "target_entity_id": entity2_id,
            "relationship_type": "assigned_to",
            "weight": 0.8,
            "confidence": 0.72,
            "attributes": {"role": "developer", "since": "2024-01-01"},
        }, headers=auth_headers_system)
        assert rel_resp.status_code == 200

        relationship = _http_json(rel_resp)
        assert _json_float(relationship, "weight") == 0.8
        assert _json_float(relationship, "confidence") == 0.72
        relationship_attrs = object_dict(relationship.get("attributes"), field="attributes")
        assert object_str(relationship_attrs.get("role"), field="role") == "developer"

    @pytest.mark.asyncio
    async def test_delete_relationship(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Удаление связи"""
        entity1_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact", "name": f"E1 {unique_id}",
        }, headers=auth_headers_system)
        entity1_id = _entity_id(entity1_resp)

        entity2_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact", "name": f"E2 {unique_id}",
        }, headers=auth_headers_system)
        entity2_id = _entity_id(entity2_resp)

        rel_resp = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": entity1_id,
            "target_entity_id": entity2_id,
            "relationship_type": "mentions",
        }, headers=auth_headers_system)
        relationship_id = _relationship_id(rel_resp)

        delete_resp = await crm_client.delete(
            f"/crm/api/v1/relationships/{relationship_id}",
            headers=auth_headers_system,
        )
        assert delete_resp.status_code == 200

        get_resp = await crm_client.get(
            f"/crm/api/v1/relationships/{relationship_id}",
            headers=auth_headers_system,
        )
        assert get_resp.status_code == 404
