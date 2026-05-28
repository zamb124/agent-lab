"""
Тесты типов сущностей и шаблонов.

User Story: Шаблоны заметок, кастомные типы для быстрого создания entities.
"""

from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_dict, object_list, object_str

pytestmark = pytest.mark.timeout(60)


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _type_id(response: Response) -> str:
    return object_str(_http_json(response).get("type_id"), field="type_id")


def _entity_type_items(response: Response) -> list[dict[str, object]]:
    return object_list(_http_json(response).get("items"))


def _type_ids_from_response(response: Response) -> list[str]:
    return [
        object_str(item.get("type_id"), field="type_id")
        for item in _entity_type_items(response)
    ]


def _attributes(entity: dict[str, object]) -> dict[str, object]:
    return object_dict(entity.get("attributes"), field="attributes")


def _required_fields_dict(entity_type: dict[str, object]) -> dict[str, object]:
    return object_dict(entity_type.get("required_fields"), field="required_fields")


def _optional_fields_dict(entity_type: dict[str, object]) -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]
    return object_dict(entity_type.get("optional_fields"), field="optional_fields")


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    for item in cast(list[object], value):
        if isinstance(item, str):
            strings.append(item)
    return strings


def _bool_field(payload: dict[str, object], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise AssertionError(f"{field} must be a bool")
    return value


def _int_field(payload: dict[str, object], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int):
        raise AssertionError(f"{field} must be an int")
    return value


def _schema_field_types(payload: dict[str, object]) -> list[dict[str, object]]:
    return object_list(payload.get("field_types"))


class TestEntityTypes:
    """Работа с типами entities и шаблонами"""

    @pytest.mark.asyncio
    async def test_system_types_initialized(
        self,
        crm_client: AsyncClient,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Системные типы минимального ядра (note, task) инициализированы"""
        response = await crm_client.get(
            "/crm/api/v1/entity-types/",
            headers=auth_headers_system,
            params={"limit": 1000, "namespace": "default"},
        )
        assert response.status_code == 200

        types = _entity_type_items(response)
        type_ids = _type_ids_from_response(response)

        assert "note" in type_ids
        assert "task" in type_ids

        for entity_type in types:
            assert entity_type["company_id"] is not None, "Все типы должны иметь company_id"

    @pytest.mark.asyncio
    async def test_create_custom_entity_type(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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

        entity_type = _http_json(response)
        assert object_str(entity_type.get("type_id"), field="type_id") == f"webinar_{unique_id}"
        assert object_str(entity_type.get("parent_type_id"), field="parent_type_id") == "note"
        assert object_str(entity_type.get("icon"), field="icon") == "🎥"
        assert "topic" in _required_fields_dict(entity_type)

    @pytest.mark.asyncio
    async def test_create_entity_with_custom_type(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Создание entity с кастомным типом"""
        _ = await crm_client.post("/crm/api/v1/entity-types/", json={
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

        entity = _http_json(entity_resp)
        assert object_str(entity.get("entity_subtype"), field="entity_subtype") == f"webinar_{unique_id}"
        attributes = _attributes(entity)
        assert object_str(attributes.get("topic"), field="topic") == "AI"
        assert _int_field(attributes, "attendees_count") == 150

    @pytest.mark.asyncio
    async def test_template_hierarchy(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Иерархия типов: parent → child"""
        type_id = f"workshop_{unique_id}"
        _ = await crm_client.post("/crm/api/v1/entity-types/", json={
            "type_id": type_id,
            "parent_type_id": "note",
            "name": "Воркшоп",
            "prompt": "Воркшоп с практическими заданиями"
        }, headers=auth_headers_system)

        # Атомарная проверка по ID — не зависит от пагинации общего списка
        # (в test-БД может накопиться много type'ов из других прогонов).
        resp = await crm_client.get(
            f"/crm/api/v1/entity-types/{type_id}",
            headers=auth_headers_system,
            params={"namespace": "default"},
        )
        assert resp.status_code == 200, resp.text
        workshop = _http_json(resp)
        assert object_str(workshop.get("type_id"), field="type_id") == type_id
        assert object_str(workshop.get("parent_type_id"), field="parent_type_id") == "note"

    @pytest.mark.asyncio
    async def test_entity_type_with_prompt(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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

        entity_type = _http_json(response)
        assert "клиента" in object_str(entity_type.get("prompt"), field="prompt")
        assert "client_name" in _required_fields_dict(entity_type)

    @pytest.mark.asyncio
    async def test_get_entity_type_by_id(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Получение типа по ID"""
        create_resp = await crm_client.post("/crm/api/v1/entity-types/", json={
            "type_id": f"custom_type_{unique_id}",
            "parent_type_id": "note",
            "name": "Кастомный тип"
        }, headers=auth_headers_system)
        type_id = _type_id(create_resp)

        get_resp = await crm_client.get(
            f"/crm/api/v1/entity-types/{type_id}",
            headers=auth_headers_system,
            params={"namespace": "default"},
        )
        assert get_resp.status_code == 200

        entity_type = _http_json(get_resp)
        assert object_str(entity_type.get("type_id"), field="type_id") == type_id
        assert object_str(entity_type.get("name"), field="name") == "Кастомный тип"

    @pytest.mark.asyncio
    async def test_update_entity_type(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Обновление типа"""
        create_resp = await crm_client.post("/crm/api/v1/entity-types/", json={
            "type_id": f"editable_type_{unique_id}",
            "parent_type_id": "note",
            "name": "Редактируемый"
        }, headers=auth_headers_system)
        type_id = _type_id(create_resp)

        update_resp = await crm_client.put(
            f"/crm/api/v1/entity-types/{type_id}",
            params={"namespace": "default"},
            json={
                "name": "Обновленное название",
                "icon": "📝",
            },
            headers=auth_headers_system,
        )
        assert update_resp.status_code == 200

        get_resp = await crm_client.get(
            f"/crm/api/v1/entity-types/{type_id}",
            headers=auth_headers_system,
            params={"namespace": "default"},
        )
        updated = _http_json(get_resp)
        assert object_str(updated.get("name"), field="name") == "Обновленное название"
        assert object_str(updated.get("icon"), field="icon") == "📝"

    @pytest.mark.asyncio
    async def test_update_entity_type_is_context_anchor(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Флаг якоря контекста на типе: запись и чтение."""
        type_id = f"anchor_flag_{unique_id}"
        create_resp = await crm_client.post(
            "/crm/api/v1/entity-types/",
            json={
                "type_id": type_id,
                "name": "Тип якоря",
                "namespace": "default",
                "is_context_anchor": False,
            },
            headers=auth_headers_system,
        )
        assert create_resp.status_code == 200
        assert _bool_field(_http_json(create_resp), "is_context_anchor") is False

        update_resp = await crm_client.put(
            f"/crm/api/v1/entity-types/{type_id}",
            params={"namespace": "default"},
            json={"is_context_anchor": True},
            headers=auth_headers_system,
        )
        assert update_resp.status_code == 200
        assert _bool_field(_http_json(update_resp), "is_context_anchor") is True

        get_resp = await crm_client.get(
            f"/crm/api/v1/entity-types/{type_id}",
            headers=auth_headers_system,
            params={"namespace": "default"},
        )
        assert _bool_field(_http_json(get_resp), "is_context_anchor") is True

    @pytest.mark.asyncio
    async def test_create_namespace_from_template(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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
        namespace = _http_json(response)
        assert object_str(namespace.get("name"), field="name") == f"sales_{unique_id}"

        namespace_types_response = await crm_client.get(
            f"/crm/api/v1/entity-types/by-namespace/sales_{unique_id}",
            headers=auth_headers_system,
        )
        assert namespace_types_response.status_code == 200
        namespace_type_ids = set(_type_ids_from_response(namespace_types_response))
        assert "note" in namespace_type_ids

    @pytest.mark.asyncio
    async def test_list_entity_types_by_namespace(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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
        types = _entity_type_items(types_response)
        assert isinstance(types, list)
        assert len(types) >= 1

    @pytest.mark.asyncio
    async def test_template_schema_options_endpoint(
        self,
        crm_client: AsyncClient,
        auth_headers_system: dict[str, str],
    ) -> None:
        response = await crm_client.get("/crm/api/v1/namespaces/templates/schema/options", headers=auth_headers_system)
        assert response.status_code == 200
        payload = _http_json(response)

        field_types = _schema_field_types(payload)
        enum_sets = object_list(payload.get("enum_sets"))
        operators = object_list(payload.get("operators"))
        assert isinstance(field_types, list)
        assert isinstance(enum_sets, list)
        assert isinstance(operators, list)
        defaults = object_dict(payload.get("defaults"), field="defaults")
        validation_limits = object_dict(payload.get("validation_limits"), field="validation_limits")
        assert object_str(defaults.get("field_type"), field="field_type") == "string"
        assert _int_field(validation_limits, "max_fields_per_section") == 128
        assert any(object_str(item.get("type_id"), field="type_id") == "enum" for item in field_types)
        assert any(object_str(item.get("type_id"), field="type_id") == "external_refs" for item in field_types)
        assert any(object_str(item.get("enum_set_id"), field="enum_set_id") == "priority" for item in enum_sets)

    @pytest.mark.asyncio
    async def test_namespace_template_crud(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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
        assert object_str(_http_json(update_resp).get("name"), field="name") == "Updated template"

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
        details = _http_json(details_resp)
        assert object_str(details.get("template_id"), field="template_id") == template_id
        assert any(
            object_str(item.get("type_id"), field="type_id") == f"type_{unique_id}"
            for item in object_list(details.get("types"))
        )

    @pytest.mark.asyncio
    async def test_namespace_editability_and_update_when_empty(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        template_id = f"ops_{unique_id}"
        namespace_name = f"ops_ns_{unique_id}"
        type_alpha = f"incident_{unique_id}"
        type_beta = f"postmortem_{unique_id}"

        create_template_resp = await crm_client.post("/crm/api/v1/namespaces/templates", json={
            "template_id": template_id,
            "name": "Operations",
            "description": "Ops template",
        }, headers=auth_headers_system)
        assert create_template_resp.status_code == 201

        create_type_alpha_resp = await crm_client.post(f"/crm/api/v1/namespaces/templates/{template_id}/types", json={
            "type_id": type_alpha,
            "name": "Инцидент",
            "required_fields": {"severity": {"type": "string"}},
            "optional_fields": {},
            "namespace_ids": [],
        }, headers=auth_headers_system)
        assert create_type_alpha_resp.status_code == 201

        create_type_beta_resp = await crm_client.post(f"/crm/api/v1/namespaces/templates/{template_id}/types", json={
            "type_id": type_beta,
            "name": "Постмортем",
            "required_fields": {"owner": {"type": "string"}},
            "optional_fields": {},
            "namespace_ids": [],
        }, headers=auth_headers_system)
        assert create_type_beta_resp.status_code == 201

        create_namespace_resp = await crm_client.post("/crm/api/v1/namespaces", json={
            "name": namespace_name,
            "description": "Ops namespace",
            "template_id": template_id,
        }, headers=auth_headers_system)
        assert create_namespace_resp.status_code == 201

        editability_resp = await crm_client.get(
            f"/crm/api/v1/namespaces/{namespace_name}/editability",
            headers=auth_headers_system,
        )
        assert editability_resp.status_code == 200
        editability = _http_json(editability_resp)
        assert object_str(editability.get("namespace"), field="namespace") == namespace_name
        assert _int_field(editability, "entity_count") == 0
        assert _bool_field(editability, "can_update_allowed_types") is True
        current_allowed_type_ids = _string_list(editability.get("current_allowed_type_ids"))
        assert type_alpha in current_allowed_type_ids
        assert type_beta in current_allowed_type_ids

        update_namespace_resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={
                "description": "Updated ops namespace",
                "allowed_type_ids": [type_alpha],
            },
            headers=auth_headers_system,
        )
        assert update_namespace_resp.status_code == 200
        assert object_str(_http_json(update_namespace_resp).get("description"), field="description") == "Updated ops namespace"

        types_by_namespace_resp = await crm_client.get(
            f"/crm/api/v1/entity-types/by-namespace/{namespace_name}",
            headers=auth_headers_system,
        )
        assert types_by_namespace_resp.status_code == 200
        type_ids = _type_ids_from_response(types_by_namespace_resp)
        assert type_alpha in type_ids
        assert type_beta not in type_ids

    @pytest.mark.asyncio
    async def test_namespace_granular_editability_with_entities(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Гранулярная editability: используемые типы залочены, неиспользуемые можно убрать, новые добавить"""
        template_id = f"sales_{unique_id}"
        namespace_name = f"sales_ns_{unique_id}"
        type_lead = f"lead_{unique_id}"
        type_deal = f"deal_{unique_id}"

        create_template_resp = await crm_client.post("/crm/api/v1/namespaces/templates", json={
            "template_id": template_id,
            "name": "Sales",
            "description": "Sales template",
        }, headers=auth_headers_system)
        assert create_template_resp.status_code == 201

        for type_id, type_name in [(type_lead, "Лид"), (type_deal, "Сделка")]:
            resp = await crm_client.post(f"/crm/api/v1/namespaces/templates/{template_id}/types", json={
                "type_id": type_id,
                "name": type_name,
                "required_fields": {"field": {"type": "string"}},
                "optional_fields": {},
                "namespace_ids": [],
            }, headers=auth_headers_system)
            assert resp.status_code == 201

        create_namespace_resp = await crm_client.post("/crm/api/v1/namespaces", json={
            "name": namespace_name,
            "description": "Sales namespace",
            "template_id": template_id,
        }, headers=auth_headers_system)
        assert create_namespace_resp.status_code == 201

        create_entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": type_lead,
            "name": f"Lead {unique_id}",
            "namespace": namespace_name,
            "attributes": {"field": "test"},
        }, headers=auth_headers_system)
        assert create_entity_resp.status_code == 200

        editability_resp = await crm_client.get(
            f"/crm/api/v1/namespaces/{namespace_name}/editability",
            headers=auth_headers_system,
        )
        assert editability_resp.status_code == 200
        editability = _http_json(editability_resp)
        assert _int_field(editability, "entity_count") >= 1
        assert _bool_field(editability, "can_add_types") is True
        locked_type_ids = _string_list(editability.get("locked_type_ids"))
        removable_type_ids = _string_list(editability.get("removable_type_ids"))
        assert type_lead in locked_type_ids
        assert type_deal in removable_type_ids
        assert type_lead not in removable_type_ids

        remove_locked_resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"allowed_type_ids": [type_deal]},
            headers=auth_headers_system,
        )
        assert remove_locked_resp.status_code == 422

        remove_unused_resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"allowed_type_ids": [type_lead]},
            headers=auth_headers_system,
        )
        assert remove_unused_resp.status_code == 200

        update_description_resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"description": "Sales namespace updated"},
            headers=auth_headers_system,
        )
        assert update_description_resp.status_code == 200
        assert object_str(_http_json(update_description_resp).get("description"), field="description") == "Sales namespace updated"
