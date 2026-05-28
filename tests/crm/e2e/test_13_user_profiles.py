"""
Тесты профилей пользователей через core API.

User Story: Профили, настройки через /api/auth/me.
"""

from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_dict, object_str


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _json_bool(payload: dict[str, object], key: str) -> bool:
    value = payload[key]
    if not isinstance(value, bool):
        raise AssertionError(f"{key} must be bool")
    return value


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    for item in cast(list[object], value):
        if isinstance(item, str):
            strings.append(item)
    return strings


class TestUserProfiles:
    """Профили пользователей через core API"""

    @pytest.mark.asyncio
    async def test_get_current_user_profile(
        self,
        crm_client: AsyncClient,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Получение профиля текущего пользователя"""
        response = await crm_client.get("/crm/api/auth/me", headers=auth_headers_system)
        assert response.status_code == 200

        profile = _http_json(response)
        assert "user_id" in profile
        assert "name" in profile
        assert "first_name" in profile
        assert "last_name" in profile
        assert "emails" in profile
        assert "phones" in profile
        assert "messengers" in profile

    @pytest.mark.asyncio
    async def test_update_user_profile(
        self,
        crm_client: AsyncClient,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Обновление профиля пользователя"""
        response = await crm_client.put("/crm/api/auth/me", json={
            "name": "Иван Иванов",
            "bio": "Менеджер по продажам",
            "phones": ["+79991234567"],
            "messengers": {"telegram": "@ivanov"},
        }, headers=auth_headers_system)
        assert response.status_code == 200

        result = _http_json(response)
        assert _json_bool(result, "success") is True

        get_resp = await crm_client.get("/crm/api/auth/me", headers=auth_headers_system)
        profile = _http_json(get_resp)
        assert object_str(profile.get("name"), field="name") == "Иван Иванов"
        assert object_str(profile.get("bio"), field="bio") == "Менеджер по продажам"
        assert "+79991234567" in _string_list(profile.get("phones"))
        messengers = object_dict(profile.get("messengers"), field="messengers")
        assert object_str(messengers.get("telegram"), field="telegram") == "@ivanov"

    @pytest.mark.asyncio
    async def test_update_profile_contacts(
        self,
        crm_client: AsyncClient,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Обновление контактов в профиле"""
        response = await crm_client.put("/crm/api/auth/me", json={
            "emails": ["ivan@company.com", "ivan@gmail.com"],
            "phones": ["+79991111111", "+79992222222"],
            "messengers": {
                "telegram": "@ivan",
                "whatsapp": "+79991111111",
                "slack": "U12345",
            },
        }, headers=auth_headers_system)
        assert response.status_code == 200

        get_resp = await crm_client.get("/crm/api/auth/me", headers=auth_headers_system)
        profile = _http_json(get_resp)
        assert len(_string_list(profile.get("emails"))) == 2
        assert len(_string_list(profile.get("phones"))) == 2
        messengers = object_dict(profile.get("messengers"), field="messengers")
        assert "telegram" in messengers
        assert "whatsapp" in messengers

    @pytest.mark.asyncio
    async def test_profile_with_ui_preferences(
        self,
        crm_client: AsyncClient,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Профиль с настройками UI"""
        response = await crm_client.put("/crm/api/auth/me", json={
            "ui_preferences": {
                "theme": "dark",
                "sidebar_collapsed": False,
                "language": "ru",
            },
        }, headers=auth_headers_system)
        assert response.status_code == 200

        get_resp = await crm_client.get("/crm/api/auth/me", headers=auth_headers_system)
        profile = _http_json(get_resp)
        ui_preferences = object_dict(profile.get("ui_preferences"), field="ui_preferences")
        assert object_str(ui_preferences.get("theme"), field="theme") == "dark"
        assert _json_bool(ui_preferences, "sidebar_collapsed") is False

    @pytest.mark.asyncio
    async def test_service_attrs_crm(
        self,
        crm_client: AsyncClient,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Service-specific атрибуты для CRM"""
        response = await crm_client.put("/crm/api/auth/me/attrs/crm", json={
            "position": "Менеджер",
            "department": "Продажи",
            "display_name": "Иван И.",
        }, headers=auth_headers_system)
        assert response.status_code == 200

        result = _http_json(response)
        assert _json_bool(result, "success") is True
        assert object_str(result.get("service"), field="service") == "crm"
        result_attrs = object_dict(result.get("attrs"), field="attrs")
        assert object_str(result_attrs.get("position"), field="position") == "Менеджер"

        get_resp = await crm_client.get("/crm/api/auth/me/attrs/crm", headers=auth_headers_system)
        assert get_resp.status_code == 200
        attrs = _http_json(get_resp)
        assert object_str(attrs.get("position"), field="position") == "Менеджер"
        assert object_str(attrs.get("department"), field="department") == "Продажи"

    @pytest.mark.asyncio
    async def test_service_attrs_multiple_services(
        self,
        crm_client: AsyncClient,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Атрибуты для нескольких сервисов"""
        _ = await crm_client.put("/crm/api/auth/me/attrs/crm", json={
            "position": "Manager",
        }, headers=auth_headers_system)

        _ = await crm_client.put("/crm/api/auth/me/attrs/agents", json={
            "favorite_agent_id": "agent_123",
        }, headers=auth_headers_system)

        _ = await crm_client.put("/crm/api/auth/me/attrs/rag", json={
            "default_namespace": "docs",
        }, headers=auth_headers_system)

        get_resp = await crm_client.get("/crm/api/auth/me", headers=auth_headers_system)
        profile = _http_json(get_resp)

        attrs_root = object_dict(profile.get("attrs"), field="attrs")
        crm_attrs = object_dict(attrs_root.get("crm"), field="crm")
        agents_attrs = object_dict(attrs_root.get("agents"), field="agents")
        rag_attrs = object_dict(attrs_root.get("rag"), field="rag")
        assert object_str(crm_attrs.get("position"), field="position") == "Manager"
        assert object_str(agents_attrs.get("favorite_agent_id"), field="favorite_agent_id") == "agent_123"
        assert object_str(rag_attrs.get("default_namespace"), field="default_namespace") == "docs"

    @pytest.mark.asyncio
    async def test_update_profile_first_last_name_syncs_display_name(
        self,
        crm_client: AsyncClient,
        auth_headers_system: dict[str, str],
    ) -> None:
        response = await crm_client.put(
            "/crm/api/auth/me",
            json={"first_name": "Пётр", "last_name": "Петров"},
            headers=auth_headers_system,
        )
        assert response.status_code == 200
        get_resp = await crm_client.get("/crm/api/auth/me", headers=auth_headers_system)
        profile = _http_json(get_resp)
        assert object_str(profile.get("first_name"), field="first_name") == "Пётр"
        assert object_str(profile.get("last_name"), field="last_name") == "Петров"
        assert object_str(profile.get("name"), field="name") == "Пётр Петров"

    @pytest.mark.asyncio
    async def test_bio_max_length_4000(
        self,
        crm_client: AsyncClient,
        auth_headers_system: dict[str, str],
    ) -> None:
        long_bio = "x" * 4000
        response = await crm_client.put(
            "/crm/api/auth/me",
            json={"bio": long_bio},
            headers=auth_headers_system,
        )
        assert response.status_code == 200
        get_resp = await crm_client.get("/crm/api/auth/me", headers=auth_headers_system)
        bio = object_str(_http_json(get_resp).get("bio"), field="bio")
        assert len(bio) == 4000
