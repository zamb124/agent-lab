"""
Тесты типов сущностей и шаблонов.

User Story: Шаблоны заметок, кастомные типы для быстрого создания entities.
"""

import pytest


class TestEntityTypes:
    """Работа с типами entities и шаблонами"""
    
    @pytest.mark.asyncio
    async def test_system_types_initialized(self, crm_client, auth_headers_system):
        """Системные типы минимального ядра (note, task) инициализированы"""
        response = await crm_client.get("/crm/api/v1/entity-types/", headers=auth_headers_system)
        assert response.status_code == 200
        
        types = response.json()
        type_ids = [t["type_id"] for t in types]
        
        assert "note" in type_ids
        assert "task" in type_ids
        
        for entity_type in types:
            assert entity_type["company_id"] is not None, "Все типы должны иметь company_id"
    
    @pytest.mark.asyncio
    async def test_create_custom_entity_type(self, crm_client, unique_id, auth_headers_system):
        """Создание кастомного подтипа note (шаблон вебинара)"""
        response = await crm_client.post("/crm/api/v1/entity-types/", json={
            "type_id": f"webinar_{unique_id}",
            "parent_type_id": "note",
            "name": "Вебинар",
            "description": "Заметки с вебинаров",
            "prompt": "Ищи информацию о вебинарах: тема, спикер, количество участников",
            "icon": "🎥",
            "required_fields": {"topic": "string", "speaker": "string"},
            "optional_fields": {"attendees_count": "int", "recording_url": "string"}
        }, headers=auth_headers_system)
        assert response.status_code == 200
        
        entity_type = response.json()
        assert entity_type["type_id"] == f"webinar_{unique_id}"
        assert entity_type["parent_type_id"] == "note"
        assert entity_type["icon"] == "🎥"
        assert "topic" in entity_type["required_fields"]
    
    @pytest.mark.asyncio
    async def test_create_entity_with_custom_type(self, crm_client, unique_id, auth_headers_system):
        """Создание entity с кастомным типом"""
        await crm_client.post("/crm/api/v1/entity-types/", json={
            "type_id": f"webinar_{unique_id}",
            "parent_type_id": "note",
            "name": "Вебинар",
            "prompt": "Ищи информацию о вебинарах",
            "icon": "🎥"
        }, headers=auth_headers_system)
        
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "entity_subtype": f"webinar_{unique_id}",
            "name": "Вебинар по AI",
            "description": "Обсудили применение AI в бизнесе",
            "attributes": {"topic": "AI", "speaker": "Иван Петров", "attendees_count": 150}
        }, headers=auth_headers_system)
        assert entity_resp.status_code == 200
        
        entity = entity_resp.json()
        assert entity["entity_subtype"] == f"webinar_{unique_id}"
        assert entity["attributes"]["topic"] == "AI"
        assert entity["attributes"]["attendees_count"] == 150
    
    @pytest.mark.asyncio
    async def test_template_hierarchy(self, crm_client, unique_id, auth_headers_system):
        """Иерархия типов: parent → child"""
        await crm_client.post("/crm/api/v1/entity-types/", json={
            "type_id": f"workshop_{unique_id}",
            "parent_type_id": "note",
            "name": "Воркшоп",
            "prompt": "Воркшоп с практическими заданиями"
        }, headers=auth_headers_system)
        
        types_resp = await crm_client.get("/crm/api/v1/entity-types/", headers=auth_headers_system)
        types = types_resp.json()
        
        workshop = next((t for t in types if t["type_id"] == f"workshop_{unique_id}"), None)
        assert workshop is not None
        assert workshop["parent_type_id"] == "note"
    
    @pytest.mark.asyncio
    async def test_entity_type_with_prompt(self, crm_client, unique_id, auth_headers_system):
        """Тип с промптом для AI извлечения"""
        response = await crm_client.post("/crm/api/v1/entity-types/", json={
            "type_id": f"client_meeting_{unique_id}",
            "parent_type_id": "note",
            "name": "Встреча с клиентом",
            "prompt": "Извлеки: имя клиента, обсуждаемые проекты, договоренности, следующие шаги",
            "required_fields": {"client_name": "string"},
            "optional_fields": {"projects": "list", "next_steps": "list"}
        }, headers=auth_headers_system)
        assert response.status_code == 200
        
        entity_type = response.json()
        assert "клиента" in entity_type["prompt"]
        assert "client_name" in entity_type["required_fields"]
    
    @pytest.mark.asyncio
    async def test_get_entity_type_by_id(self, crm_client, unique_id, auth_headers_system):
        """Получение типа по ID"""
        create_resp = await crm_client.post("/crm/api/v1/entity-types/", json={
            "type_id": f"custom_type_{unique_id}",
            "parent_type_id": "note",
            "name": "Кастомный тип"
        }, headers=auth_headers_system)
        type_id = create_resp.json()["type_id"]
        
        get_resp = await crm_client.get(f"/crm/api/v1/entity-types/{type_id}", headers=auth_headers_system)
        assert get_resp.status_code == 200
        
        entity_type = get_resp.json()
        assert entity_type["type_id"] == type_id
        assert entity_type["name"] == "Кастомный тип"
    
    @pytest.mark.asyncio
    async def test_update_entity_type(self, crm_client, unique_id, auth_headers_system):
        """Обновление типа"""
        create_resp = await crm_client.post("/crm/api/v1/entity-types/", json={
            "type_id": f"editable_type_{unique_id}",
            "parent_type_id": "note",
            "name": "Редактируемый"
        }, headers=auth_headers_system)
        type_id = create_resp.json()["type_id"]
        
        update_resp = await crm_client.put(f"/crm/api/v1/entity-types/{type_id}", json={
            "name": "Обновленное название",
            "icon": "📝"
        }, headers=auth_headers_system)
        assert update_resp.status_code == 200
        
        get_resp = await crm_client.get(f"/crm/api/v1/entity-types/{type_id}", headers=auth_headers_system)
        updated = get_resp.json()
        assert updated["name"] == "Обновленное название"
        assert updated["icon"] == "📝"

    @pytest.mark.asyncio
    async def test_create_namespace_from_template(self, crm_client, unique_id, auth_headers_system):
        create_template_response = await crm_client.post("/crm/api/v1/namespaces/templates", json={
            "template_id": f"sales_{unique_id}",
            "name": "Sales template",
            "description": "sales custom",
        }, headers=auth_headers_system)
        assert create_template_response.status_code == 201

        create_template_type_response = await crm_client.post(f"/crm/api/v1/namespaces/templates/sales_{unique_id}/types", json={
            "type_id": f"lead_{unique_id}",
            "name": "Лид",
            "prompt": "Ищи лидов",
            "required_fields": {"source": {"type": "string"}},
            "optional_fields": {},
            "namespace_ids": [],
        }, headers=auth_headers_system)
        assert create_template_type_response.status_code == 201

        response = await crm_client.post("/crm/api/v1/namespaces", json={
            "name": f"sales_{unique_id}",
            "description": "Пространство продаж",
            "template_id": f"sales_{unique_id}",
        }, headers=auth_headers_system)
        assert response.status_code == 201
        namespace = response.json()
        assert namespace["name"] == f"sales_{unique_id}"

    @pytest.mark.asyncio
    async def test_list_entity_types_by_namespace(self, crm_client, unique_id, auth_headers_system):
        namespace_name = f"dev_{unique_id}"
        create_template_response = await crm_client.post("/crm/api/v1/namespaces/templates", json={
            "template_id": f"development_{unique_id}",
            "name": "Development template",
        }, headers=auth_headers_system)
        assert create_template_response.status_code == 201

        create_template_type_response = await crm_client.post(f"/crm/api/v1/namespaces/templates/development_{unique_id}/types", json={
            "type_id": f"incident_{unique_id}",
            "name": "Инцидент",
            "required_fields": {"severity": {"type": "string"}},
            "optional_fields": {},
            "namespace_ids": [],
        }, headers=auth_headers_system)
        assert create_template_type_response.status_code == 201

        create_namespace_resp = await crm_client.post("/crm/api/v1/namespaces", json={
            "name": namespace_name,
            "description": "Пространство разработки",
            "template_id": f"development_{unique_id}",
        }, headers=auth_headers_system)
        assert create_namespace_resp.status_code == 201

        types_response = await crm_client.get(f"/crm/api/v1/entity-types/by-namespace/{namespace_name}", headers=auth_headers_system)
        assert types_response.status_code == 200
        types = types_response.json()
        assert isinstance(types, list)
        assert len(types) >= 1

    @pytest.mark.asyncio
    async def test_namespace_template_crud(self, crm_client, unique_id, auth_headers_system):
        template_id = f"tmpl_{unique_id}"
        create_resp = await crm_client.post("/crm/api/v1/namespaces/templates", json={
            "template_id": template_id,
            "name": "Custom template",
            "description": "For CRUD",
        }, headers=auth_headers_system)
        assert create_resp.status_code == 201

        update_resp = await crm_client.put(f"/crm/api/v1/namespaces/templates/{template_id}", json={
            "name": "Updated template",
            "description": "Updated description",
        }, headers=auth_headers_system)
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "Updated template"

        type_resp = await crm_client.post(f"/crm/api/v1/namespaces/templates/{template_id}/types", json={
            "type_id": f"type_{unique_id}",
            "name": "Type in template",
            "required_fields": {"field_a": {"type": "string"}},
            "optional_fields": {"field_b": {"type": "string"}},
            "namespace_ids": [],
        }, headers=auth_headers_system)
        assert type_resp.status_code == 201

        details_resp = await crm_client.get(f"/crm/api/v1/namespaces/templates/{template_id}", headers=auth_headers_system)
        assert details_resp.status_code == 200
        details = details_resp.json()
        assert details["template_id"] == template_id
        assert any(item["type_id"] == f"type_{unique_id}" for item in details["types"])

