"""
Тесты CRUD операций с entities.

User Story: Базовые операции создания, чтения, обновления и удаления entities.
"""

from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_dict, object_list, object_str

pytestmark = pytest.mark.timeout(20, func_only=True)


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _entity_id(response: Response) -> str:
    return object_str(_http_json(response).get("entity_id"), field="entity_id")


def _query_items(response: Response) -> list[dict[str, object]]:
    return object_list(_http_json(response).get("items"))


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    for item in cast(list[object], value):
        if isinstance(item, str):
            strings.append(item)
    return strings


def _delete_success(response: Response) -> bool:
    success = _http_json(response).get("success")
    if not isinstance(success, bool):
        raise AssertionError("success must be a bool")
    return success


class TestEntityLifecycle:
    """Полный жизненный цикл entity"""

    @pytest.mark.asyncio
    async def test_create_note(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Создание note entity"""
        response = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": f"Встреча {unique_id}",
                "description": "Обсудили проект X",
            },
            headers=auth_headers_system,
        )
        assert response.status_code == 200

        entity = _http_json(response)
        assert object_str(entity.get("entity_type"), field="entity_type") == "note"
        assert entity.get("entity_subtype") is None
        assert object_str(entity.get("name"), field="name") == f"Встреча {unique_id}"
        assert "entity_id" in entity
        assert "company_id" in entity

    @pytest.mark.asyncio
    async def test_create_and_get_entity(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Создание и получение entity по ID"""
        create_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Звонок {unique_id}",
            "description": "Обсудили условия контракта",
            "tags": ["важно", "контракт"],
        }, headers=auth_headers_system)
        assert create_resp.status_code == 200
        entity_id = _entity_id(create_resp)

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        assert get_resp.status_code == 200

        retrieved = _http_json(get_resp)
        assert object_str(retrieved.get("entity_id"), field="entity_id") == entity_id
        assert object_str(retrieved.get("name"), field="name") == f"Звонок {unique_id}"
        assert retrieved.get("entity_subtype") is None
        assert "важно" in _string_list(retrieved.get("tags"))

    @pytest.mark.asyncio
    async def test_update_entity(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Обновление полей entity"""
        create_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Задача {unique_id}",
            "priority": "low",
            "status": "pending",
        }, headers=auth_headers_system)
        entity_id = _entity_id(create_resp)

        update_resp = await crm_client.put(f"/crm/api/v1/entities/{entity_id}", json={
            "priority": "urgent",
            "status": "in_progress",
            "description": "Добавлено описание",
        }, headers=auth_headers_system)
        assert update_resp.status_code == 200

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        updated = _http_json(get_resp)
        assert object_str(updated.get("priority"), field="priority") == "urgent"
        assert object_str(updated.get("status"), field="status") == "in_progress"
        assert object_str(updated.get("description"), field="description") == "Добавлено описание"

    @pytest.mark.asyncio
    async def test_delete_entity(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Удаление entity"""
        create_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Удаляемая заметка {unique_id}",
        }, headers=auth_headers_system)
        entity_id = _entity_id(create_resp)

        delete_resp = await crm_client.delete(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        assert delete_resp.status_code == 200
        assert _delete_success(delete_resp) is True

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_entities_no_filter(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Получение списка всех entities"""
        test_user_id = f"test_user_{unique_id}"

        for i in range(3):
            _ = await crm_client.post("/crm/api/v1/entities/", json={
                "entity_type": "note",
                "name": f"Note {i} {unique_id}",
                "user_id": test_user_id,
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

        entities = _query_items(list_resp)
        assert len(entities) >= 3

        for entity in entities:
            assert object_str(entity.get("user_id"), field="user_id") == test_user_id

    @pytest.mark.asyncio
    async def test_list_entities_with_type_filter(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Список с фильтрацией по типу"""
        test_user_id = f"test_user_{unique_id}"

        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Meeting {unique_id}",
            "user_id": test_user_id,
        }, headers=auth_headers_system)
        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Task {unique_id}",
            "user_id": test_user_id,
        }, headers=auth_headers_system)
        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Call {unique_id}",
            "user_id": test_user_id,
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
        entities = _query_items(list_resp)

        assert len(entities) >= 2

        for entity in entities:
            assert object_str(entity.get("entity_type"), field="entity_type") == "note"
            assert object_str(entity.get("user_id"), field="user_id") == test_user_id

    @pytest.mark.asyncio
    async def test_list_entities_with_subtype_filter(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Список с фильтрацией по подтипу"""
        test_user_id = f"test_user_{unique_id}"
        meeting_subtype = f"meeting_{unique_id}"

        create_subtype_resp = await crm_client.post("/crm/api/v1/entity-types/", json={
            "type_id": meeting_subtype,
            "parent_type_id": "note",
            "name": "Meeting",
            "namespace": "default",
        }, headers=auth_headers_system)
        assert create_subtype_resp.status_code == 200

        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "entity_subtype": meeting_subtype,
            "name": f"Meeting 1 {unique_id}",
            "user_id": test_user_id,
        }, headers=auth_headers_system)
        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "entity_subtype": meeting_subtype,
            "name": f"Meeting 2 {unique_id}",
            "user_id": test_user_id,
        }, headers=auth_headers_system)

        list_resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": "note",
                "entity_subtype": meeting_subtype,
                "limit": 100,
                "filters": {"field": "user_id", "op": "$eq", "value": test_user_id},
            },
            headers=auth_headers_system,
        )
        entities = _query_items(list_resp)

        assert len(entities) >= 2

        for entity in entities:
            assert object_str(entity.get("entity_subtype"), field="entity_subtype") == meeting_subtype
            assert object_str(entity.get("user_id"), field="user_id") == test_user_id

    @pytest.mark.asyncio
    async def test_create_custom_entity(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Создание entity пользовательского типа из шаблона namespace."""
        template_id = f"custom_{unique_id}"
        candidate_type_id = f"candidate_{unique_id}"
        namespace_name = f"custom_ns_{unique_id}"

        create_template_resp = await crm_client.post("/crm/api/v1/namespaces/templates", json={
            "template_id": template_id,
            "name": "Custom template",
            "description": "Template for custom types",
        }, headers=auth_headers_system)
        assert create_template_resp.status_code == 201

        upsert_type_resp = await crm_client.post(
            f"/crm/api/v1/namespaces/templates/{template_id}/types",
            json={
                "type_id": candidate_type_id,
                "name": "Кандидат",
                "required_fields": {"phone": {"type": "string"}},
                "optional_fields": {"role": {"type": "string"}},
                "namespace_ids": [],
            },
            headers=auth_headers_system,
        )
        assert upsert_type_resp.status_code == 201

        create_namespace_resp = await crm_client.post("/crm/api/v1/namespaces", json={
            "name": namespace_name,
            "description": "custom namespace",
            "template_id": template_id,
        }, headers=auth_headers_system)
        assert create_namespace_resp.status_code == 201

        response = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": candidate_type_id,
            "name": f"Иван Иванов {unique_id}",
            "namespace": namespace_name,
            "attributes": {
                "phone": "+79991234567",
                "email": "ivan@example.com",
                "role": "менеджер",
            },
        }, headers=auth_headers_system)
        assert response.status_code == 200

        entity = _http_json(response)
        assert object_str(entity.get("entity_type"), field="entity_type") == candidate_type_id
        attributes = object_dict(entity.get("attributes"), field="attributes")
        assert object_str(attributes.get("phone"), field="phone") == "+79991234567"
        assert object_str(attributes.get("role"), field="role") == "менеджер"

    @pytest.mark.asyncio
    async def test_create_entity_with_all_fields(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Создание entity со всеми опциональными полями"""
        response = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Полная задача {unique_id}",
            "description": "Детальное описание задачи",
            "tags": ["срочно", "проект"],
            "attributes": {"project": "X", "sprint": 5},
            "priority": "high",
            "due_date": "2024-12-31",
            "assignees": ["user1", "user2"],
        }, headers=auth_headers_system)
        assert response.status_code == 200

        entity = _http_json(response)
        assert object_str(entity.get("name"), field="name") == f"Полная задача {unique_id}"
        assert object_str(entity.get("priority"), field="priority") == "high"
        assert object_str(entity.get("due_date"), field="due_date") == "2024-12-31"
        assert len(_string_list(entity.get("assignees"))) == 2
        assert "срочно" in _string_list(entity.get("tags"))

    @pytest.mark.asyncio
    async def test_create_entity_rejects_type_outside_namespace(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        candidate_type_id = f"candidate_{unique_id}"
        namespace_name = f"hr_{unique_id}"

        create_type_resp = await crm_client.post("/crm/api/v1/entity-types/", json={
            "type_id": candidate_type_id,
            "name": "Кандидат",
            "description": "HR сущность",
            "namespace": "default",
        }, headers=auth_headers_system)
        assert create_type_resp.status_code == 200

        create_namespace_resp = await crm_client.post("/crm/api/v1/namespaces", json={
            "name": namespace_name,
            "description": "HR пространство",
            "template_id": "hr",
        }, headers=auth_headers_system)
        assert create_namespace_resp.status_code == 201

        create_entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": candidate_type_id,
            "name": "Иван Кандидат",
            "namespace": namespace_name,
        }, headers=auth_headers_system)
        assert create_entity_resp.status_code == 422
