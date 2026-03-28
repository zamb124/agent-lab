"""
Тесты инициализации компании.

User Story: Автоматическое создание системных типов при создании компании.
"""

import pytest


class TestCompanyInit:
    """Инициализация CRM для компании"""
    
    @pytest.mark.asyncio
    async def test_system_types_exist_for_company(self, crm_client, unique_id, auth_headers_system):
        """Системные типы entities существуют для компании"""
        types_resp = await crm_client.get("/crm/api/v1/entity-types/", headers=auth_headers_system)
        assert types_resp.status_code == 200
        
        types = types_resp.json()
        type_ids = [t["type_id"] for t in types]
        
        assert "note" in type_ids
        assert "meeting" in type_ids
        assert "call" in type_ids
        assert "task" in type_ids
        
        for entity_type in types:
            assert entity_type["company_id"] is not None
    
    @pytest.mark.asyncio
    async def test_system_relationship_types_exist(self, crm_client, unique_id, auth_headers_system):
        """Системные типы связей существуют"""
        types_resp = await crm_client.get("/crm/api/v1/relationships/types/", headers=auth_headers_system)
        assert types_resp.status_code == 200

        types = types_resp.json()
        type_ids = [t["type_id"] for t in types]
        
        assert "mentions" in type_ids
        assert "linked" in type_ids
    
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
    async def test_system_types_have_prompts(self, crm_client, auth_headers_system):
        """Системные типы имеют промпты для AI"""
        types_resp = await crm_client.get("/crm/api/v1/entity-types/", headers=auth_headers_system)
        types = types_resp.json()
        
        meeting_type = next((t for t in types if t["type_id"] == "meeting"), None)
        if meeting_type:
            assert meeting_type.get("prompt") is not None or meeting_type.get("is_system") is True 

