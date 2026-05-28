"""
Тесты карточек сущностей со связями.

User Story: Просмотр entity с полным контекстом и связанными entities.
"""

from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_dict, object_list, object_str


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _entity_id(response: Response) -> str:
    return object_str(_http_json(response).get("entity_id"), field="entity_id")


def _card_entity(card: dict[str, object]) -> dict[str, object]:
    return object_dict(card.get("entity"), field="entity")


def _card_relationships(card: dict[str, object]) -> list[dict[str, object]]:
    return object_list(card.get("relationships"))


def _card_related_entities(card: dict[str, object]) -> list[dict[str, object]]:
    return object_list(card.get("related_entities"))


class TestEntityCards:
    """Карточки entities со связями"""

    @pytest.mark.asyncio
    async def test_get_entity_card_with_relationships(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Карточка entity со всеми связями и связанными entities"""
        main_entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Main Contact {unique_id}",
            "attributes": {"role": "менеджер"},
        }, headers=auth_headers_system)
        main_entity_id = _entity_id(main_entity_resp)

        related1_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "project",
            "name": f"Project A {unique_id}",
        }, headers=auth_headers_system)
        related1_id = _entity_id(related1_resp)

        related2_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "organization",
            "name": f"Company X {unique_id}",
        }, headers=auth_headers_system)
        related2_id = _entity_id(related2_resp)

        _ = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": main_entity_id,
            "target_entity_id": related1_id,
            "relationship_type": "assigned_to",
        }, headers=auth_headers_system)

        _ = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": main_entity_id,
            "target_entity_id": related2_id,
            "relationship_type": "belongs_to",
        }, headers=auth_headers_system)

        card_resp = await crm_client.get(
            f"/crm/api/v1/entities/{main_entity_id}/card",
            headers=auth_headers_system,
        )
        assert card_resp.status_code == 200

        card = _http_json(card_resp)
        entity = _card_entity(card)
        assert object_str(entity.get("entity_id"), field="entity_id") == main_entity_id
        relationships = _card_relationships(card)
        assert len(relationships) >= 2
        assert all("confidence" in relationship for relationship in relationships)
        assert "related_entities" in card

    @pytest.mark.asyncio
    async def test_company_card_with_people_and_projects(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Карточка компании с людьми и проектами"""
        company_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "organization",
            "name": f"Company {unique_id}",
        }, headers=auth_headers_system)
        company_id = _entity_id(company_resp)

        person1_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Employee 1 {unique_id}",
        }, headers=auth_headers_system)
        person1_id = _entity_id(person1_resp)

        person2_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Employee 2 {unique_id}",
        }, headers=auth_headers_system)
        person2_id = _entity_id(person2_resp)

        project_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "project",
            "name": f"Company Project {unique_id}",
        }, headers=auth_headers_system)
        project_id = _entity_id(project_resp)

        for person_id in (person1_id, person2_id):
            _ = await crm_client.post("/crm/api/v1/relationships/", json={
                "source_entity_id": person_id,
                "target_entity_id": company_id,
                "relationship_type": "belongs_to",
            }, headers=auth_headers_system)

        _ = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": company_id,
            "target_entity_id": project_id,
            "relationship_type": "parent_of",
        }, headers=auth_headers_system)

        card_resp = await crm_client.get(
            f"/crm/api/v1/entities/{company_id}/card",
            headers=auth_headers_system,
        )
        card = _http_json(card_resp)

        assert object_str(_card_entity(card).get("entity_type"), field="entity_type") == "organization"
        assert len(_card_relationships(card)) >= 3

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_project_card_with_team(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Карточка проекта с командой"""
        project_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "project",
            "name": f"Project {unique_id}",
            "attributes": {"status": "active"},
        }, headers=auth_headers_system)
        project_id = _entity_id(project_resp)

        team_member_ids: list[str] = []
        for i in range(3):
            resp = await crm_client.post("/crm/api/v1/entities/", json={
                "entity_type": "contact",
                "name": f"Team Member {i} {unique_id}",
                "attributes": {"role": f"role_{i}"},
            }, headers=auth_headers_system)
            team_member_ids.append(_entity_id(resp))

        for member_id in team_member_ids:
            _ = await crm_client.post("/crm/api/v1/relationships/", json={
                "source_entity_id": member_id,
                "target_entity_id": project_id,
                "relationship_type": "assigned_to",
            }, headers=auth_headers_system)

        card_resp = await crm_client.get(
            f"/crm/api/v1/entities/{project_id}/card",
            headers=auth_headers_system,
        )
        card = _http_json(card_resp)

        assert object_str(_card_entity(card).get("entity_type"), field="entity_type") == "project"
        assert len(_card_relationships(card)) >= 3
        assert len(_card_related_entities(card)) >= 3
