"""
Тесты карточек сущностей со связями.

User Story: Просмотр entity с полным контекстом и связанными entities.
"""

import pytest


class TestEntityCards:
    """Карточки entities со связями"""

    @pytest.mark.asyncio
    async def test_get_entity_card_with_relationships(self, crm_client, unique_id, auth_headers_system):
        """Карточка entity со всеми связями и связанными entities"""
        main_entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Main Contact {unique_id}",
            "attributes": {"role": "менеджер"}
        }, headers=auth_headers_system)
        main_entity_id = main_entity_resp.json()["entity_id"]

        related1_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "project",
            "name": f"Project A {unique_id}"
        }, headers=auth_headers_system)
        related1_id = related1_resp.json()["entity_id"]

        related2_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "organization",
            "name": f"Company X {unique_id}"
        }, headers=auth_headers_system)
        related2_id = related2_resp.json()["entity_id"]

        await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": main_entity_id,
            "target_entity_id": related1_id,
            "relationship_type": "assigned_to"
        }, headers=auth_headers_system)

        await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": main_entity_id,
            "target_entity_id": related2_id,
            "relationship_type": "belongs_to"
        }, headers=auth_headers_system)

        card_resp = await crm_client.get(f"/crm/api/v1/entities/{main_entity_id}/card", headers=auth_headers_system)
        assert card_resp.status_code == 200

        card = card_resp.json()
        assert "entity" in card
        assert card["entity"]["entity_id"] == main_entity_id
        assert "relationships" in card
        assert len(card["relationships"]) >= 2
        assert all("confidence" in r for r in card["relationships"])
        assert "related_entities" in card

    @pytest.mark.asyncio
    async def test_company_card_with_people_and_projects(self, crm_client, unique_id, auth_headers_system):
        """Карточка компании с людьми и проектами"""
        company_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "organization",
            "name": f"Company {unique_id}"
        }, headers=auth_headers_system)
        company_id = company_resp.json()["entity_id"]

        person1_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Employee 1 {unique_id}"
        }, headers=auth_headers_system)
        person1_id = person1_resp.json()["entity_id"]

        person2_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Employee 2 {unique_id}"
        }, headers=auth_headers_system)
        person2_id = person2_resp.json()["entity_id"]

        project_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "project",
            "name": f"Company Project {unique_id}"
        }, headers=auth_headers_system)
        project_id = project_resp.json()["entity_id"]

        for person_id in [person1_id, person2_id]:
            await crm_client.post("/crm/api/v1/relationships/", json={
                "source_entity_id": person_id,
                "target_entity_id": company_id,
                "relationship_type": "belongs_to"
            }, headers=auth_headers_system)

        await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": company_id,
            "target_entity_id": project_id,
            "relationship_type": "parent_of"
        }, headers=auth_headers_system)

        card_resp = await crm_client.get(f"/crm/api/v1/entities/{company_id}/card", headers=auth_headers_system)
        card = card_resp.json()

        assert card["entity"]["entity_type"] == "organization"
        assert len(card["relationships"]) >= 3

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_project_card_with_team(self, crm_client, unique_id, auth_headers_system):
        """Карточка проекта с командой"""
        project_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "project",
            "name": f"Project {unique_id}",
            "attributes": {"status": "active"}
        }, headers=auth_headers_system)
        project_id = project_resp.json()["entity_id"]

        team_member_ids = []
        for i in range(3):
            resp = await crm_client.post("/crm/api/v1/entities/", json={
                "entity_type": "contact",
                "name": f"Team Member {i} {unique_id}",
                "attributes": {"role": f"role_{i}"}
            }, headers=auth_headers_system)
            team_member_ids.append(resp.json()["entity_id"])

        for member_id in team_member_ids:
            await crm_client.post("/crm/api/v1/relationships/", json={
                "source_entity_id": member_id,
                "target_entity_id": project_id,
                "relationship_type": "assigned_to"
            }, headers=auth_headers_system)

        card_resp = await crm_client.get(f"/crm/api/v1/entities/{project_id}/card", headers=auth_headers_system)
        card = card_resp.json()

        assert card["entity"]["entity_type"] == "project"
        assert len(card["relationships"]) >= 3
        assert len(card["related_entities"]) >= 3

