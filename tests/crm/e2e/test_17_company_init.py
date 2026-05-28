"""
Тесты инициализации компании.

User Story: Автоматическое создание системных типов при создании компании.
"""

from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_list, object_str

pytestmark = pytest.mark.timeout(60)


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _entity_id(response: Response) -> str:
    return object_str(_http_json(response).get("entity_id"), field="entity_id")


def _detail_text(response: Response) -> str:
    detail = _http_json(response).get("detail")
    if isinstance(detail, str):
        return detail
    return str(detail)


def _entity_type_items(response: Response) -> list[dict[str, object]]:
    return object_list(_http_json(response).get("items"))


def _relationship_type_items(response: Response) -> list[dict[str, object]]:
    return object_list(_http_json(response).get("items"))


def _entity_types_by_id(response: Response) -> dict[str, dict[str, object]]:
    return {
        object_str(item.get("type_id"), field="type_id"): item
        for item in _entity_type_items(response)
    }


def _relationship_types_by_id(response: Response) -> dict[str, dict[str, object]]:
    return {
        object_str(item.get("type_id"), field="type_id"): item
        for item in _relationship_type_items(response)
    }


def _query_items(response: Response) -> list[dict[str, object]]:
    return object_list(_http_json(response).get("items"))


def _bool_field(row: dict[str, object], field: str) -> bool:
    value = row.get(field)
    if not isinstance(value, bool):
        raise AssertionError(f"{field} must be a bool")
    return value


class TestCompanyInit:
    """Инициализация CRM для компании"""

    @pytest.mark.asyncio
    async def test_system_types_exist_for_company(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Системные типы минимального ядра существуют для компании"""
        _ = unique_id
        types_resp = await crm_client.get(
            "/crm/api/v1/entity-types/",
            headers=auth_headers_system,
            params={"limit": 1000, "namespace": "default"},
        )
        assert types_resp.status_code == 200

        types = _entity_type_items(types_resp)
        type_ids = [object_str(entity_type.get("type_id"), field="type_id") for entity_type in types]
        types_by_id = _entity_types_by_id(types_resp)

        for expected_type_id in (
            "note",
            "task",
            "contact",
            "member",
            "company",
            "namespace",
            "organization",
            "project",
            "topic",
        ):
            assert expected_type_id in type_ids

        for entity_type in types:
            assert entity_type.get("company_id") is not None

        member_type = types_by_id["member"]
        assert _bool_field(member_type, "is_voice_target") is True
        assert _bool_field(member_type, "extractable") is False
        assert _bool_field(member_type, "is_context_anchor") is False
        assert object_str(member_type.get("namespace"), field="namespace") == "default"

        contact_type = types_by_id["contact"]
        assert _bool_field(contact_type, "is_voice_target") is True

        company_type = types_by_id["company"]
        assert _bool_field(company_type, "extractable") is False
        assert _bool_field(company_type, "is_context_anchor") is False
        assert object_str(company_type.get("namespace"), field="namespace") == "default"

        namespace_type = types_by_id["namespace"]
        assert _bool_field(namespace_type, "extractable") is False
        assert object_str(namespace_type.get("namespace"), field="namespace") == "default"

    @pytest.mark.asyncio
    async def test_system_relationship_types_exist(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Все системные типы связей существуют и неизменяемы"""
        _ = unique_id
        types_resp = await crm_client.get(
            "/crm/api/v1/relationships/types/",
            headers=auth_headers_system,
            params={"limit": 1000},
        )
        assert types_resp.status_code == 200

        types = _relationship_type_items(types_resp)
        type_id_set = {object_str(row.get("type_id"), field="type_id") for row in types}
        assert len(types) == len(type_id_set), (
            "Список типов связей не должен содержать дубли type_id (разные company_id в одной выдаче)"
        )
        types_by_id = _relationship_types_by_id(types_resp)

        expected_type_ids = [
            "mentions",
            "linked",
            "related_to",
            "parent_of",
            "child_of",
            "assigned_to",
            "belongs_to",
            "follows_up",
            "blocks",
            "blocked_by",
            "duplicates",
            "note_voice",
            "in_context",
        ]
        for expected_id in expected_type_ids:
            assert expected_id in types_by_id, f"Системный тип связи '{expected_id}' отсутствует"
            assert _bool_field(types_by_id[expected_id], "is_system") is True, (
                f"Тип '{expected_id}' должен быть системным"
            )

    @pytest.mark.asyncio
    async def test_custom_relationship_type_creation_allowed(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Создание кастомных типов связей через API доступно"""
        resp = await crm_client.post("/crm/api/v1/relationships/types/", json={
            "type_id": f"custom_rel_{unique_id}",
            "name": "Кастомная связь",
            "is_directed": True,
        }, headers=auth_headers_system)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_company_entity_organization_created(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Entity типа 'organization' для компании создается автоматически"""
        _ = unique_id
        orgs_resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={"entity_type": "organization", "limit": 100},
            headers=auth_headers_system,
        )
        assert orgs_resp.status_code == 200
        orgs = _query_items(orgs_resp)

        assert len(orgs) >= 1

        own_org: dict[str, object] | None = None
        for organization in orgs:
            if organization.get("is_owner"):
                own_org = organization
                break
        if own_org is not None:
            assert object_str(own_org.get("entity_type"), field="entity_type") == "organization"

    @pytest.mark.asyncio
    async def test_system_entity_types_have_prompts(
        self,
        crm_client: AsyncClient,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Системные типы сущностей имеют промпты для AI"""
        types_resp = await crm_client.get(
            "/crm/api/v1/entity-types/",
            headers=auth_headers_system,
            params={"limit": 1000, "namespace": "default"},
        )
        types = _entity_type_items(types_resp)

        note_type: dict[str, object] | None = None
        for entity_type in types:
            if object_str(entity_type.get("type_id"), field="type_id") == "note":
                note_type = entity_type
                break
        assert note_type is not None
        assert note_type.get("prompt") is not None or _bool_field(note_type, "is_system") is True

    @pytest.mark.asyncio
    async def test_system_relationship_types_have_prompts(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Системные типы связей с AI-промптами: mentions, related_to, parent_of, assigned_to, belongs_to, follows_up, blocks"""
        _ = unique_id
        types_resp = await crm_client.get(
            "/crm/api/v1/relationships/types/",
            headers=auth_headers_system,
            params={"limit": 1000},
        )
        assert types_resp.status_code == 200

        types_by_id = _relationship_types_by_id(types_resp)

        types_with_prompts = [
            "mentions",
            "related_to",
            "parent_of",
            "assigned_to",
            "belongs_to",
            "follows_up",
            "blocks",
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
    async def test_relationship_type_validation_on_create(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Создание связи с несуществующим типом возвращает 422"""
        entity1_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note {unique_id}",
        }, headers=auth_headers_system)
        entity1_id = _entity_id(entity1_resp)

        entity2_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note2 {unique_id}",
        }, headers=auth_headers_system)
        entity2_id = _entity_id(entity2_resp)

        resp = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": entity1_id,
            "target_entity_id": entity2_id,
            "relationship_type": f"nonexistent_type_{unique_id}",
        }, headers=auth_headers_system)
        assert resp.status_code == 422
        assert "Unknown relationship_type" in _detail_text(resp)
