"""
Тесты гранулярной editability namespace.

Проверяет все сценарии безопасного редактирования пространств:
- добавление типов всегда разрешено
- удаление используемых типов запрещено
- удаление неиспользуемых типов разрешено
- редактирование prompt/description/name типа всегда разрешено
- type_id неизменяем
- описание namespace можно менять всегда
"""

from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_dict, object_list, object_str

pytestmark = pytest.mark.timeout(60)


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    for item in cast(list[object], value):
        if isinstance(item, str):
            strings.append(item)
    return strings


def _int_field(payload: dict[str, object], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int):
        raise AssertionError(f"{field} must be an int")
    return value


def _bool_field(payload: dict[str, object], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise AssertionError(f"{field} must be a bool")
    return value


def _detail_text(response: Response) -> str:
    detail = _http_json(response).get("detail")
    if isinstance(detail, str):
        return detail
    return str(detail)


def _entity_type_items(response: Response) -> list[dict[str, object]]:
    return object_list(_http_json(response).get("items"))


def _type_id_set(response: Response) -> set[str]:
    return {
        object_str(item.get("type_id"), field="type_id")
        for item in _entity_type_items(response)
    }


async def _create_namespace_with_types(
    crm_client: AsyncClient,
    headers: dict[str, str],
    unique_id: str,
    type_ids: list[str],
) -> tuple[str, str]:
    """Хелпер: создает шаблон, типы и namespace."""
    template_id = f"tmpl_{unique_id}"
    namespace_name = f"ns_{unique_id}"

    resp = await crm_client.post("/crm/api/v1/namespaces/templates", json={
        "template_id": template_id,
        "name": f"Template {unique_id}",
    }, headers=headers)
    assert resp.status_code == 201

    for type_id in type_ids:
        type_resp = await crm_client.post(
            f"/crm/api/v1/namespaces/templates/{template_id}/types",
            json={
                "type_id": type_id,
                "name": f"Type {type_id}",
                "required_fields": {},
                "optional_fields": {},
                "namespace_ids": [],
            },
            headers=headers,
        )
        assert type_resp.status_code == 201

    namespace_resp = await crm_client.post("/crm/api/v1/namespaces", json={
        "name": namespace_name,
        "description": f"Namespace {unique_id}",
        "template_id": template_id,
    }, headers=headers)
    assert namespace_resp.status_code == 201

    return namespace_name, template_id


class TestNamespaceEditabilityEmpty:
    """Editability для пустого namespace (без сущностей)"""

    @pytest.mark.asyncio
    async def test_empty_namespace_all_types_removable(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """В пустом namespace все типы можно убрать"""
        type_a = f"alpha_{unique_id}"
        type_b = f"beta_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_a, type_b],
        )

        resp = await crm_client.get(
            f"/crm/api/v1/namespaces/{namespace_name}/editability",
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        editability = _http_json(resp)

        assert _int_field(editability, "entity_count") == 0
        assert _bool_field(editability, "has_entities") is False
        assert _bool_field(editability, "can_add_types") is True
        assert _bool_field(editability, "can_update_allowed_types") is True
        locked_type_ids = _string_list(editability.get("locked_type_ids"))
        removable_type_ids = _string_list(editability.get("removable_type_ids"))
        current_allowed_type_ids = _string_list(editability.get("current_allowed_type_ids"))
        assert locked_type_ids == []
        assert type_a in removable_type_ids
        assert type_b in removable_type_ids
        assert type_a in current_allowed_type_ids
        assert type_b in current_allowed_type_ids
        all_namespaces_type_ids = _string_list(editability.get("all_namespaces_type_ids"))
        assert isinstance(all_namespaces_type_ids, list)
        assert len(all_namespaces_type_ids) >= 1

    @pytest.mark.asyncio
    async def test_empty_namespace_can_remove_all_types(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """В пустом namespace можно убрать все пользовательские типы"""
        type_a = f"alpha_{unique_id}"
        type_b = f"beta_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_a, type_b],
        )

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"allowed_type_ids": []},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200

        types_resp = await crm_client.get(
            f"/crm/api/v1/entity-types/by-namespace/{namespace_name}",
            headers=auth_headers_system,
        )
        assert types_resp.status_code == 200
        remaining_type_ids = _type_id_set(types_resp)
        assert type_a not in remaining_type_ids
        assert type_b not in remaining_type_ids
        for entity_type_row in _entity_type_items(types_resp):
            assert object_str(entity_type_row.get("namespace"), field="namespace") == namespace_name

    @pytest.mark.asyncio
    async def test_empty_namespace_description_always_editable(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Описание пустого namespace всегда можно менять"""
        type_a = f"alpha_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_a],
        )

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"description": "Обновленное описание"},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        assert object_str(_http_json(resp).get("description"), field="description") == "Обновленное описание"


class TestNamespaceEditabilityWithEntities:
    """Editability когда в namespace есть сущности"""

    @pytest.mark.asyncio
    async def test_used_type_locked_unused_removable(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Тип с сущностями залочен, тип без сущностей можно убрать"""
        type_used = f"used_{unique_id}"
        type_unused = f"unused_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_used, type_unused],
        )

        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": type_used,
            "name": f"Entity {unique_id}",
            "namespace": namespace_name,
        }, headers=auth_headers_system)

        resp = await crm_client.get(
            f"/crm/api/v1/namespaces/{namespace_name}/editability",
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        editability = _http_json(resp)

        assert _int_field(editability, "entity_count") >= 1
        assert _bool_field(editability, "has_entities") is True
        assert _bool_field(editability, "can_add_types") is True
        locked_type_ids = _string_list(editability.get("locked_type_ids"))
        removable_type_ids = _string_list(editability.get("removable_type_ids"))
        assert type_used in locked_type_ids
        assert type_unused in removable_type_ids
        assert type_used not in removable_type_ids
        assert type_unused not in locked_type_ids

    @pytest.mark.asyncio
    async def test_cannot_remove_used_type(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """422 при попытке убрать тип с сущностями"""
        type_used = f"used_{unique_id}"
        type_unused = f"unused_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_used, type_unused],
        )

        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": type_used,
            "name": f"Entity {unique_id}",
            "namespace": namespace_name,
        }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"allowed_type_ids": [type_unused]},
            headers=auth_headers_system,
        )
        assert resp.status_code == 422
        assert type_used in _detail_text(resp)

    @pytest.mark.asyncio
    async def test_can_remove_unused_type_when_entities_exist(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Можно убрать неиспользуемый тип, даже если в namespace есть сущности другого типа"""
        type_used = f"used_{unique_id}"
        type_unused = f"unused_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_used, type_unused],
        )

        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": type_used,
            "name": f"Entity {unique_id}",
            "namespace": namespace_name,
        }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"allowed_type_ids": [type_used]},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200

        types_resp = await crm_client.get(
            f"/crm/api/v1/entity-types/by-namespace/{namespace_name}",
            headers=auth_headers_system,
        )
        type_ids = _type_id_set(types_resp)
        assert type_used in type_ids
        assert type_unused not in type_ids

    @pytest.mark.asyncio
    async def test_can_add_new_type_when_entities_exist(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Можно добавить новый тип в namespace с сущностями"""
        type_existing = f"exist_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_existing],
        )

        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": type_existing,
            "name": f"Entity {unique_id}",
            "namespace": namespace_name,
        }, headers=auth_headers_system)

        extra_type_id = f"extra_{unique_id}"
        _ = await crm_client.post("/crm/api/v1/entity-types", json={
            "type_id": extra_type_id,
            "name": "Extra Type",
            "namespace": "default",
        }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"allowed_type_ids": [type_existing, extra_type_id]},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200

        types_resp = await crm_client.get(
            f"/crm/api/v1/entity-types/by-namespace/{namespace_name}",
            headers=auth_headers_system,
        )
        type_ids = _type_id_set(types_resp)
        assert type_existing in type_ids
        assert extra_type_id in type_ids

    @pytest.mark.asyncio
    async def test_description_editable_with_entities(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Описание namespace можно менять при наличии сущностей"""
        type_a = f"alpha_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_a],
        )

        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": type_a,
            "name": f"Entity {unique_id}",
            "namespace": namespace_name,
        }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"description": "Новое описание с сущностями"},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        assert (
            object_str(_http_json(resp).get("description"), field="description")
            == "Новое описание с сущностями"
        )

    @pytest.mark.asyncio
    async def test_cannot_remove_multiple_used_types(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """422 при попытке убрать несколько используемых типов"""
        type_a = f"a_{unique_id}"
        type_b = f"b_{unique_id}"
        type_c = f"c_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_a, type_b, type_c],
        )

        for type_id in (type_a, type_b):
            _ = await crm_client.post("/crm/api/v1/entities/", json={
                "entity_type": type_id,
                "name": f"Entity {type_id}",
                "namespace": namespace_name,
            }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"allowed_type_ids": [type_c]},
            headers=auth_headers_system,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_add_and_remove_simultaneously(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Можно одновременно добавить новый тип и убрать неиспользуемый"""
        type_used = f"used_{unique_id}"
        type_removable = f"rmv_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_used, type_removable],
        )

        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": type_used,
            "name": f"Entity {unique_id}",
            "namespace": namespace_name,
        }, headers=auth_headers_system)

        type_added = f"added_{unique_id}"
        _ = await crm_client.post("/crm/api/v1/entity-types", json={
            "type_id": type_added,
            "name": "Added Type",
            "namespace": "default",
        }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"allowed_type_ids": [type_used, type_added]},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200

        types_resp = await crm_client.get(
            f"/crm/api/v1/entity-types/by-namespace/{namespace_name}",
            headers=auth_headers_system,
        )
        type_ids = _type_id_set(types_resp)
        assert type_used in type_ids
        assert type_added in type_ids
        assert type_removable not in type_ids


class TestEntityTypeImmutability:
    """type_id неизменяем, но prompt/description/name можно менять"""

    @pytest.mark.asyncio
    async def test_can_update_prompt_and_description(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Prompt и описание типа можно менять через PUT /entity-types/{type_id}"""
        type_id = f"editable_{unique_id}"
        _ = await crm_client.post("/crm/api/v1/entity-types", json={
            "type_id": type_id,
            "name": "Тестовый тип",
            "prompt": "Старый промпт",
            "description": "Старое описание",
        }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/entity-types/{type_id}",
            params={"namespace": "default"},
            json={
                "prompt": "Новый промпт для AI-извлечения",
                "description": "Новое описание типа",
            },
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        updated = _http_json(resp)
        assert object_str(updated.get("prompt"), field="prompt") == "Новый промпт для AI-извлечения"
        assert object_str(updated.get("description"), field="description") == "Новое описание типа"
        assert object_str(updated.get("type_id"), field="type_id") == type_id

    @pytest.mark.asyncio
    async def test_can_update_name_icon_color(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Название, иконку и цвет можно менять"""
        type_id = f"visual_{unique_id}"
        _ = await crm_client.post("/crm/api/v1/entity-types", json={
            "type_id": type_id,
            "name": "Старое название",
            "icon": "folder",
            "color": "#000000",
        }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/entity-types/{type_id}",
            params={"namespace": "default"},
            json={
                "name": "Обновленное название",
                "icon": "star",
                "color": "#FF5722",
            },
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        updated = _http_json(resp)
        assert object_str(updated.get("name"), field="name") == "Обновленное название"
        assert object_str(updated.get("icon"), field="icon") == "star"
        assert object_str(updated.get("color"), field="color") == "#FF5722"

    @pytest.mark.asyncio
    async def test_can_update_required_optional_fields(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Схему полей можно менять"""
        type_id = f"schema_{unique_id}"
        _ = await crm_client.post("/crm/api/v1/entity-types", json={
            "type_id": type_id,
            "name": "Schema Type",
            "required_fields": {"old_field": {"type": "string"}},
            "optional_fields": {},
        }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/entity-types/{type_id}",
            params={"namespace": "default"},
            json={
                "required_fields": {"new_field": {"type": "number", "label": "Число"}},
                "optional_fields": {"extra": {"type": "string", "label": "Доп"}},
            },
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        updated = _http_json(resp)
        required_fields = object_dict(updated.get("required_fields"), field="required_fields")
        optional_fields = object_dict(updated.get("optional_fields"), field="optional_fields")
        assert "new_field" in required_fields
        assert "extra" in optional_fields

    @pytest.mark.asyncio
    async def test_type_id_not_changeable_via_path(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """type_id определяется path-параметром и не меняется"""
        type_id = f"immutable_{unique_id}"
        _ = await crm_client.post("/crm/api/v1/entity-types", json={
            "type_id": type_id,
            "name": "Immutable ID",
        }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/entity-types/{type_id}",
            params={"namespace": "default"},
            json={
                "name": "Changed Name Only",
            },
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        assert object_str(_http_json(resp).get("type_id"), field="type_id") == type_id

    @pytest.mark.asyncio
    async def test_can_update_type_with_existing_entities(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Метаданные типа можно менять даже если есть сущности этого типа"""
        type_id = f"inuse_{unique_id}"
        _ = await crm_client.post("/crm/api/v1/entity-types", json={
            "type_id": type_id,
            "name": "In Use Type",
            "prompt": "Старый промпт",
        }, headers=auth_headers_system)

        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": type_id,
            "name": f"Entity {unique_id}",
        }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/entity-types/{type_id}",
            params={"namespace": "default"},
            json={
                "name": "Updated In Use Type",
                "prompt": "Обновленный промпт для типа с данными",
                "description": "Тип с данными, описание обновлено",
            },
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        updated = _http_json(resp)
        assert object_str(updated.get("name"), field="name") == "Updated In Use Type"
        assert object_str(updated.get("prompt"), field="prompt") == "Обновленный промпт для типа с данными"
        assert object_str(updated.get("type_id"), field="type_id") == type_id


class TestNamespaceEditabilityEdgeCases:
    """Граничные сценарии"""

    @pytest.mark.asyncio
    async def test_unknown_type_ids_rejected(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """422 при передаче несуществующих type_id"""
        type_a = f"alpha_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_a],
        )

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"allowed_type_ids": [type_a, "nonexistent_type_xyz"]},
            headers=auth_headers_system,
        )
        assert resp.status_code == 422
        assert "nonexistent_type_xyz" in _detail_text(resp)

    @pytest.mark.asyncio
    async def test_editability_reflects_multiple_entity_types(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """locked_type_ids содержит все типы с сущностями"""
        type_a = f"a_{unique_id}"
        type_b = f"b_{unique_id}"
        type_c = f"c_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_a, type_b, type_c],
        )

        for type_id in (type_a, type_c):
            _ = await crm_client.post("/crm/api/v1/entities/", json={
                "entity_type": type_id,
                "name": f"Entity {type_id}",
                "namespace": namespace_name,
            }, headers=auth_headers_system)

        resp = await crm_client.get(
            f"/crm/api/v1/namespaces/{namespace_name}/editability",
            headers=auth_headers_system,
        )
        editability = _http_json(resp)
        locked_type_ids = _string_list(editability.get("locked_type_ids"))
        removable_type_ids = _string_list(editability.get("removable_type_ids"))
        assert type_a in locked_type_ids
        assert type_c in locked_type_ids
        assert type_b in removable_type_ids
        assert type_b not in locked_type_ids

    @pytest.mark.asyncio
    async def test_keep_locked_types_and_add_new(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Можно оставить все залоченные типы и добавить новый одним запросом"""
        type_locked = f"locked_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_locked],
        )

        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": type_locked,
            "name": f"Entity {unique_id}",
            "namespace": namespace_name,
        }, headers=auth_headers_system)

        type_added = f"new_{unique_id}"
        _ = await crm_client.post("/crm/api/v1/entity-types", json={
            "type_id": type_added,
            "name": "Новый тип",
            "namespace": "default",
        }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"allowed_type_ids": [type_locked, type_added]},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200

        editability_resp = await crm_client.get(
            f"/crm/api/v1/namespaces/{namespace_name}/editability",
            headers=auth_headers_system,
        )
        editability = _http_json(editability_resp)
        current_allowed_type_ids = _string_list(editability.get("current_allowed_type_ids"))
        assert type_locked in current_allowed_type_ids
        assert type_added in current_allowed_type_ids

    @pytest.mark.asyncio
    async def test_nonexistent_namespace_editability_404(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """404 для несуществующего namespace"""
        resp = await crm_client.get(
            f"/crm/api/v1/namespaces/nonexistent_{unique_id}/editability",
            headers=auth_headers_system,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_namespace_update_404(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """404 при обновлении несуществующего namespace"""
        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/nonexistent_{unique_id}",
            json={"description": "test"},
            headers=auth_headers_system,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_description_and_types_in_single_request(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Можно менять и описание, и типы одним запросом"""
        type_a = f"alpha_{unique_id}"
        type_b = f"beta_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_a, type_b],
        )

        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": type_a,
            "name": f"Entity {unique_id}",
            "namespace": namespace_name,
        }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={
                "description": "Комбинированное обновление",
                "allowed_type_ids": [type_a],
            },
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        assert (
            object_str(_http_json(resp).get("description"), field="description")
            == "Комбинированное обновление"
        )

        types_resp = await crm_client.get(
            f"/crm/api/v1/entity-types/by-namespace/{namespace_name}",
            headers=auth_headers_system,
        )
        type_ids = _type_id_set(types_resp)
        assert type_a in type_ids
        assert type_b not in type_ids
