"""
Тесты фильтрации и семантического поиска.

User Story: Поиск по дате, владельцу, тексту, тегам, сущностям.
"""

import pytest
from datetime import date, timedelta


class TestFilteringSearch:
    """Фильтрация и поиск"""
    
    @pytest.mark.asyncio
    async def test_filter_by_date_range(self, crm_client, unique_id, auth_headers_system):
        """Фильтр по диапазону дат создания"""
        test_user_id = f"test_user_{unique_id}"
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Today note {unique_id}",
            "note_date": today.isoformat(),
            "user_id": test_user_id
        }, headers=auth_headers_system)
        
        resp = await crm_client.get(
            f"/crm/api/v1/entities/?entity_type=note&user_id={test_user_id}&date_from={today.isoformat()}&date_to={today.isoformat()}"
        , headers=auth_headers_system)
        entities = resp.json()
        assert len(entities) >= 1
        for e in entities:
            assert e["user_id"] == test_user_id
    
    @pytest.mark.asyncio
    async def test_filter_by_tags(self, crm_client, unique_id, auth_headers_system):
        """Фильтр по тегам"""
        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Tagged note {unique_id}",
            "tags": ["важно", "проект-x", unique_id]
        }, headers=auth_headers_system)
        
        resp = await crm_client.get(f"/crm/api/v1/entities/?tags=важно", headers=auth_headers_system)
        entities = resp.json()
        tagged = [e for e in entities if unique_id in e.get("tags", [])]
        assert len(tagged) >= 1
    
    @pytest.mark.asyncio
    async def test_semantic_search(self, crm_client, unique_id, auth_headers_system):
        """Семантический поиск - проверяем что endpoint работает"""
        unique_phrase = f"уникальная_фраза_{unique_id}"
        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Searchable note {unique_id}",
            "description": f"Содержит {unique_phrase} для поиска"
        }, headers=auth_headers_system)
        
        # В тестах используются mock embeddings (случайные), поэтому просто проверяем что endpoint работает
        search_resp = await crm_client.get(f"/crm/api/v1/entities/search?query={unique_id}", headers=auth_headers_system)
        assert search_resp.status_code == 200
        
        results = search_resp.json()
        # Проверяем что хоть что-то вернулось
        assert isinstance(results, list)
    
    @pytest.mark.asyncio
    async def test_combined_filters(self, crm_client, unique_id, auth_headers_system):
        """Комбинированные фильтры: тип + подтип + тег"""
        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "entity_subtype": "meeting",
            "name": f"Complex filter {unique_id}",
            "tags": ["фильтр", unique_id]
        }, headers=auth_headers_system)
        
        resp = await crm_client.get(
            f"/crm/api/v1/entities/?entity_type=note&entity_subtype=meeting&tags=фильтр"
        , headers=auth_headers_system)
        entities = resp.json()
        found = [e for e in entities if unique_id in e.get("tags", [])]
        assert len(found) >= 1
    
    @pytest.mark.asyncio
    async def test_search_by_entity_name(self, crm_client, unique_id, auth_headers_system):
        """Поиск по имени entity"""
        unique_name = f"Уникальное_имя_{unique_id}"
        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": unique_name
        }, headers=auth_headers_system)
        
        search_resp = await crm_client.get(f"/crm/api/v1/entities/search?query={unique_name}", headers=auth_headers_system)
        results = search_resp.json()
        found = [r for r in results if r["name"] == unique_name]
        assert len(found) >= 1

