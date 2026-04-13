"""
Тесты CRUD операций с entities.

User Story: Базовые операции создания, чтения, обновления и удаления entities.
"""

import pytest

pytestmark = pytest.mark.timeout(20, func_only=True)


class TestEntityLifecycle:
    """Полный жизненный цикл entity"""
    
    @pytest.mark.asyncio
    async def test_create_note(self, crm_client, unique_id, auth_headers_system):
        """Создание note entity"""
        response = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": f"Встреча {unique_id}",
                "description": "Обсудили проект X"
            },
            headers=auth_headers_system)
        assert response.status_code == 200
        
        entity = response.json()
        assert entity["entity_type"] == "note"
        assert entity["entity_subtype"] is None
        assert entity["name"] == f"Встреча {unique_id}"
        assert "entity_id" in entity
        assert "company_id" in entity
    
    @pytest.mark.asyncio
    async def test_create_and_get_entity(self, crm_client, unique_id, auth_headers_system):
        """Создание и получение entity по ID"""
        create_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Звонок {unique_id}",
            "description": "Обсудили условия контракта",
            "tags": ["важно", "контракт"]
        }, headers=auth_headers_system)
        assert create_resp.status_code == 200
        entity_id = create_resp.json()["entity_id"]
        
        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        assert get_resp.status_code == 200
        
        retrieved = get_resp.json()
        assert retrieved["entity_id"] == entity_id
        assert retrieved["name"] == f"Звонок {unique_id}"
        assert retrieved["entity_subtype"] is None
        assert "важно" in retrieved["tags"]
    
    @pytest.mark.asyncio
    async def test_update_entity(self, crm_client, unique_id, auth_headers_system):
        """Обновление полей entity"""
        create_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Задача {unique_id}",
            "priority": "low",
            "status": "pending"
        }, headers=auth_headers_system)
        entity_id = create_resp.json()["entity_id"]
        
        update_resp = await crm_client.put(f"/crm/api/v1/entities/{entity_id}", json={
            "priority": "urgent",
            "status": "in_progress",
            "description": "Добавлено описание"
        }, headers=auth_headers_system)
        assert update_resp.status_code == 200
        
        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        updated = get_resp.json()
        assert updated["priority"] == "urgent"
        assert updated["status"] == "in_progress"
        assert updated["description"] == "Добавлено описание"
    
    @pytest.mark.asyncio
    async def test_delete_entity(self, crm_client, unique_id, auth_headers_system):
        """Удаление entity"""
        create_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Удаляемая заметка {unique_id}"
        }, headers=auth_headers_system)
        entity_id = create_resp.json()["entity_id"]
        
        delete_resp = await crm_client.delete(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        assert delete_resp.status_code == 200
        assert delete_resp.json()["success"] is True
        
        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        assert get_resp.status_code == 404
    
    @pytest.mark.asyncio
    async def test_list_entities_no_filter(self, crm_client, unique_id, auth_headers_system):
        """Получение списка всех entities"""
        test_user_id = f"test_user_{unique_id}"
        
        for i in range(3):
            await crm_client.post("/crm/api/v1/entities/", json={
                "entity_type": "note",
                "name": f"Note {i} {unique_id}",
                "user_id": test_user_id
            }, headers=auth_headers_system)
        
        list_resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "limit": 100,
                "filters": {"field": "user_id", "op": "$eq", "value": test_user_id},
            },
            headers=auth_headers_system,
        )
        assert list_resp.status_code == 200
        
        payload = list_resp.json()
        entities = payload["items"]
        assert isinstance(entities, list)
        assert len(entities) >= 3
        
        for entity in entities:
            assert entity["user_id"] == test_user_id
    
    @pytest.mark.asyncio
    async def test_list_entities_with_type_filter(self, crm_client, unique_id, auth_headers_system):
        """Список с фильтрацией по типу"""
        test_user_id = f"test_user_{unique_id}"
        
        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Meeting {unique_id}",
            "user_id": test_user_id
        }, headers=auth_headers_system)
        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Task {unique_id}",
            "user_id": test_user_id
        }, headers=auth_headers_system)
        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Call {unique_id}",
            "user_id": test_user_id
        }, headers=auth_headers_system)
        
        list_resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": "note",
                "limit": 100,
                "filters": {"field": "user_id", "op": "$eq", "value": test_user_id},
            },
            headers=auth_headers_system,
        )
        entities = list_resp.json()["items"]
        
        assert len(entities) >= 2
        
        for entity in entities:
            assert entity["entity_type"] == "note"
            assert entity["user_id"] == test_user_id
    
    @pytest.mark.asyncio
    async def test_list_entities_with_subtype_filter(self, crm_client, unique_id, auth_headers_system):
        """Список с фильтрацией по подтипу"""
        test_user_id = f"test_user_{unique_id}"

        create_subtype_resp = await crm_client.post("/crm/api/v1/entity-types/", json={
            "type_id": f"meeting_{unique_id}",
            "parent_type_id": "note",
            "name": "Meeting",
            "namespace_ids": ["default"],
        }, headers=auth_headers_system)
        assert create_subtype_resp.status_code == 200

        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "entity_subtype": f"meeting_{unique_id}",
            "name": f"Meeting 1 {unique_id}",
            "user_id": test_user_id
        }, headers=auth_headers_system)
        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "entity_subtype": f"meeting_{unique_id}",
            "name": f"Meeting 2 {unique_id}",
            "user_id": test_user_id
        }, headers=auth_headers_system)

        list_resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": "note",
                "entity_subtype": f"meeting_{unique_id}",
                "limit": 100,
                "filters": {"field": "user_id", "op": "$eq", "value": test_user_id},
            },
            headers=auth_headers_system,
        )
        entities = list_resp.json()["items"]
        
        assert len(entities) >= 2
        
        for entity in entities:
            assert entity["entity_subtype"] == f"meeting_{unique_id}"
            assert entity["user_id"] == test_user_id
    
    @pytest.mark.asyncio
    async def test_create_custom_entity(self, crm_client, unique_id, auth_headers_system):
        """Создание entity пользовательского типа из шаблона namespace."""
        create_template_resp = await crm_client.post("/crm/api/v1/namespaces/templates", json={
            "template_id": f"custom_{unique_id}",
            "name": "Custom template",
            "description": "Template for custom types",
        }, headers=auth_headers_system)
        assert create_template_resp.status_code == 201

        upsert_type_resp = await crm_client.post(f"/crm/api/v1/namespaces/templates/custom_{unique_id}/types", json={
            "type_id": f"candidate_{unique_id}",
            "name": "Кандидат",
            "required_fields": {"phone": {"type": "string"}},
            "optional_fields": {"role": {"type": "string"}},
            "namespace_ids": [],
        }, headers=auth_headers_system)
        assert upsert_type_resp.status_code == 201

        create_namespace_resp = await crm_client.post("/crm/api/v1/namespaces", json={
            "name": f"custom_ns_{unique_id}",
            "description": "custom namespace",
            "template_id": f"custom_{unique_id}",
        }, headers=auth_headers_system)
        assert create_namespace_resp.status_code == 201

        response = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": f"candidate_{unique_id}",
            "name": f"Иван Иванов {unique_id}",
            "namespace": f"custom_ns_{unique_id}",
            "attributes": {
                "phone": "+79991234567",
                "email": "ivan@example.com",
                "role": "менеджер"
            }
        }, headers=auth_headers_system)
        assert response.status_code == 200
        
        entity = response.json()
        assert entity["entity_type"] == f"candidate_{unique_id}"
        assert entity["attributes"]["phone"] == "+79991234567"
        assert entity["attributes"]["role"] == "менеджер"
    
    @pytest.mark.asyncio
    async def test_create_entity_with_all_fields(self, crm_client, unique_id, auth_headers_system):
        """Создание entity со всеми опциональными полями"""
        response = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Полная задача {unique_id}",
            "description": "Детальное описание задачи",
            "tags": ["срочно", "проект"],
            "attributes": {"project": "X", "sprint": 5},
            "priority": "high",
            "due_date": "2024-12-31",
            "assignees": ["user1", "user2"]
        }, headers=auth_headers_system)
        assert response.status_code == 200
        
        entity = response.json()
        assert entity["name"] == f"Полная задача {unique_id}"
        assert entity["priority"] == "high"
        assert entity["due_date"] == "2024-12-31"
        assert len(entity["assignees"]) == 2
        assert "срочно" in entity["tags"]

    @pytest.mark.asyncio
    async def test_create_entity_rejects_type_outside_namespace(self, crm_client, unique_id, auth_headers_system):
        create_type_resp = await crm_client.post("/crm/api/v1/entity-types/", json={
            "type_id": f"candidate_{unique_id}",
            "name": "Кандидат",
            "description": "HR сущность",
            "namespace_ids": ["default"],
        }, headers=auth_headers_system)
        assert create_type_resp.status_code == 200

        create_namespace_resp = await crm_client.post("/crm/api/v1/namespaces", json={
            "name": f"hr_{unique_id}",
            "description": "HR пространство",
            "template_id": "hr",
        }, headers=auth_headers_system)
        assert create_namespace_resp.status_code == 201

        create_entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": f"candidate_{unique_id}",
            "name": "Иван Кандидат",
            "namespace": f"hr_{unique_id}",
        }, headers=auth_headers_system)
        assert create_entity_resp.status_code == 422

