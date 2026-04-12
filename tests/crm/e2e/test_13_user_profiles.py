"""
Тесты профилей пользователей через core API.

User Story: Профили, настройки через /api/auth/me.
"""

import pytest


class TestUserProfiles:
    """Профили пользователей через core API"""
    
    @pytest.mark.asyncio
    async def test_get_current_user_profile(self, crm_client, auth_headers_system):
        """Получение профиля текущего пользователя"""
        response = await crm_client.get("/crm/api/auth/me", headers=auth_headers_system)
        assert response.status_code == 200
        
        profile = response.json()
        assert "user_id" in profile
        assert "name" in profile
        assert "first_name" in profile
        assert "last_name" in profile
        assert "emails" in profile
        assert "phones" in profile
        assert "messengers" in profile
    
    @pytest.mark.asyncio
    async def test_update_user_profile(self, crm_client, auth_headers_system):
        """Обновление профиля пользователя"""
        response = await crm_client.put("/crm/api/auth/me", json={
            "name": "Иван Иванов",
            "bio": "Менеджер по продажам",
            "phones": ["+79991234567"],
            "messengers": {"telegram": "@ivanov"}
        }, headers=auth_headers_system)
        assert response.status_code == 200
        
        result = response.json()
        assert result["success"] is True
        
        get_resp = await crm_client.get("/crm/api/auth/me", headers=auth_headers_system)
        profile = get_resp.json()
        assert profile["name"] == "Иван Иванов"
        assert profile["bio"] == "Менеджер по продажам"
        assert "+79991234567" in profile["phones"]
        assert profile["messengers"]["telegram"] == "@ivanov"
    
    @pytest.mark.asyncio
    async def test_update_profile_contacts(self, crm_client, auth_headers_system):
        """Обновление контактов в профиле"""
        response = await crm_client.put("/crm/api/auth/me", json={
            "emails": ["ivan@company.com", "ivan@gmail.com"],
            "phones": ["+79991111111", "+79992222222"],
            "messengers": {
                "telegram": "@ivan",
                "whatsapp": "+79991111111",
                "slack": "U12345"
            }
        }, headers=auth_headers_system)
        assert response.status_code == 200
        
        get_resp = await crm_client.get("/crm/api/auth/me", headers=auth_headers_system)
        profile = get_resp.json()
        assert len(profile["emails"]) == 2
        assert len(profile["phones"]) == 2
        assert "telegram" in profile["messengers"]
        assert "whatsapp" in profile["messengers"]
    
    @pytest.mark.asyncio
    async def test_profile_with_ui_preferences(self, crm_client, auth_headers_system):
        """Профиль с настройками UI"""
        response = await crm_client.put("/crm/api/auth/me", json={
            "ui_preferences": {
                "theme": "dark",
                "sidebar_collapsed": False,
                "language": "ru"
            }
        }, headers=auth_headers_system)
        assert response.status_code == 200
        
        get_resp = await crm_client.get("/crm/api/auth/me", headers=auth_headers_system)
        profile = get_resp.json()
        assert profile["ui_preferences"]["theme"] == "dark"
        assert profile["ui_preferences"]["sidebar_collapsed"] is False
    
    @pytest.mark.asyncio
    async def test_service_attrs_crm(self, crm_client, auth_headers_system):
        """Service-specific атрибуты для CRM"""
        response = await crm_client.put("/crm/api/auth/me/attrs/crm", json={
            "position": "Менеджер",
            "department": "Продажи",
            "display_name": "Иван И."
        }, headers=auth_headers_system)
        assert response.status_code == 200
        
        result = response.json()
        assert result["success"] is True
        assert result["service"] == "crm"
        assert result["attrs"]["position"] == "Менеджер"
        
        get_resp = await crm_client.get("/crm/api/auth/me/attrs/crm", headers=auth_headers_system)
        assert get_resp.status_code == 200
        attrs = get_resp.json()
        assert attrs["position"] == "Менеджер"
        assert attrs["department"] == "Продажи"
    
    @pytest.mark.asyncio
    async def test_service_attrs_multiple_services(self, crm_client, auth_headers_system):
        """Атрибуты для нескольких сервисов"""
        await crm_client.put("/crm/api/auth/me/attrs/crm", json={
            "position": "Manager"
        }, headers=auth_headers_system)
        
        await crm_client.put("/crm/api/auth/me/attrs/agents", json={
            "favorite_agent_id": "agent_123"
        }, headers=auth_headers_system)
        
        await crm_client.put("/crm/api/auth/me/attrs/rag", json={
            "default_namespace": "docs"
        }, headers=auth_headers_system)
        
        get_resp = await crm_client.get("/crm/api/auth/me", headers=auth_headers_system)
        profile = get_resp.json()
        
        assert profile["attrs"]["crm"]["position"] == "Manager"
        assert profile["attrs"]["agents"]["favorite_agent_id"] == "agent_123"
        assert profile["attrs"]["rag"]["default_namespace"] == "docs"

    @pytest.mark.asyncio
    async def test_update_profile_first_last_name_syncs_display_name(
        self, crm_client, auth_headers_system
    ):
        response = await crm_client.put(
            "/crm/api/auth/me",
            json={"first_name": "Пётр", "last_name": "Петров"},
            headers=auth_headers_system,
        )
        assert response.status_code == 200
        get_resp = await crm_client.get("/crm/api/auth/me", headers=auth_headers_system)
        profile = get_resp.json()
        assert profile["first_name"] == "Пётр"
        assert profile["last_name"] == "Петров"
        assert profile["name"] == "Пётр Петров"

    @pytest.mark.asyncio
    async def test_bio_max_length_4000(self, crm_client, auth_headers_system):
        long_bio = "x" * 4000
        response = await crm_client.put(
            "/crm/api/auth/me",
            json={"bio": long_bio},
            headers=auth_headers_system,
        )
        assert response.status_code == 200
        get_resp = await crm_client.get("/crm/api/auth/me", headers=auth_headers_system)
        assert len(get_resp.json()["bio"]) == 4000
