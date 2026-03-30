"""
Тесты инициализации компании.

User Story: Автоматическое создание системных типов при создании компании.
"""

import pytest


class TestCompanyInit:
    """Инициализация CRM для компании"""
    
    @pytest.mark.asyncio
    async def test_system_types_exist_for_company(self, crm_client, unique_id, auth_headers_system):
        """Системные типы минимального ядра (note, task) существуют для компании"""
        types_resp = await crm_client.get("/crm/api/v1/entity-types/", headers=auth_headers_system)
        assert types_resp.status_code == 200
        
        types = types_resp.json()
        type_ids = [t["type_id"] for t in types]
        
        assert "note" in type_ids
        assert "task" in type_ids
        
        for entity_type in types:
            assert entity_type["company_id"] is not None
    
    @pytest.mark.asyncio
    async def test_system_relationship_types_exist(self, crm_client, unique_id, auth_headers_system):
        """Все 11 системных типов связей существуют и неизменяемы"""
        types_resp = await crm_client.get("/crm/api/v1/relationships/types/", headers=auth_headers_system)
        assert types_resp.status_code == 200

        types = types_resp.json()
        types_by_id = {t["type_id"]: t for t in types}

        expected_type_ids = [
            "mentions", "linked", "related_to",
            "parent_of", "child_of",
            "assigned_to", "belongs_to", "follows_up",
            "blocks", "blocked_by", "duplicates",
        ]
        for expected_id in expected_type_ids:
            assert expected_id in types_by_id, f"Системный тип связи '{expected_id}' отсутствует"
            assert types_by_id[expected_id]["is_system"] is True, (
                f"Тип '{expected_id}' должен быть системным"
            )

    @pytest.mark.asyncio
    async def test_custom_relationship_type_creation_allowed(self, crm_client, unique_id, auth_headers_system):
        """Создание кастомных типов связей через API доступно"""
        resp = await crm_client.post("/crm/api/v1/relationships/types/", json={
            "type_id": f"custom_rel_{unique_id}",
            "name": "Кастомная связь",
            "is_directed": True,
        }, headers=auth_headers_system)
        assert resp.status_code == 200
    
    @pytest.mark.asyncio
    async def test_company_entity_organization_created(self, crm_client, unique_id, auth_headers_system):
        """Entity типа 'organization' для компании создается автоматически"""
        orgs_resp = await crm_client.get("/crm/api/v1/entities/?entity_type=organization", headers=auth_headers_system)
        orgs = orgs_resp.json()
        
        assert len(orgs) >= 1
        
        own_org = next((o for o in orgs if o.get("is_owner")), None)
        if own_org:
            assert own_org["entity_type"] == "organization"
    
    @pytest.mark.asyncio
    async def test_system_entity_types_have_prompts(self, crm_client, auth_headers_system):
        """Системные типы сущностей имеют промпты для AI"""
        types_resp = await crm_client.get("/crm/api/v1/entity-types/", headers=auth_headers_system)
        types = types_resp.json()
        
        note_type = next((t for t in types if t["type_id"] == "note"), None)
        assert note_type is not None
        assert note_type.get("prompt") is not None or note_type.get("is_system") is True

    @pytest.mark.asyncio
    async def test_system_relationship_types_have_prompts(self, crm_client, unique_id, auth_headers_system):
        """Системные типы связей с AI-промптами: mentions, related_to, parent_of, assigned_to, belongs_to, follows_up, blocks"""
        types_resp = await crm_client.get("/crm/api/v1/relationships/types/", headers=auth_headers_system)
        assert types_resp.status_code == 200

        types_by_id = {t["type_id"]: t for t in types_resp.json()}

        types_with_prompts = [
            "mentions", "related_to", "parent_of",
            "assigned_to", "belongs_to", "follows_up", "blocks",
        ]
        for type_id in types_with_prompts:
            rel_type = types_by_id.get(type_id)
            assert rel_type is not None, f"Тип '{type_id}' не найден"
            assert rel_type.get("prompt") is not None, (
                f"Тип '{type_id}' должен иметь prompt для AI"
            )

        types_without_prompts = ["linked", "child_of", "blocked_by", "duplicates"]
        for type_id in types_without_prompts:
            rel_type = types_by_id.get(type_id)
            assert rel_type is not None, f"Тип '{type_id}' не найден"
            assert rel_type.get("prompt") is None, (
                f"Тип '{type_id}' не должен иметь prompt (inverse/системный)"
            )

    @pytest.mark.asyncio
    async def test_relationship_type_validation_on_create(self, crm_client, unique_id, auth_headers_system):
        """Создание связи с несуществующим типом возвращает 422"""
        entity1_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note {unique_id}",
        }, headers=auth_headers_system)
        entity1_id = entity1_resp.json()["entity_id"]

        entity2_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note2 {unique_id}",
        }, headers=auth_headers_system)
        entity2_id = entity2_resp.json()["entity_id"]

        resp = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": entity1_id,
            "target_entity_id": entity2_id,
            "relationship_type": f"nonexistent_type_{unique_id}",
        }, headers=auth_headers_system)
        assert resp.status_code == 422
        assert "Unknown relationship_type" in resp.json()["detail"]
