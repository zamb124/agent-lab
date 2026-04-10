"""
Тесты фильтрации и семантического поиска.

User Story: Поиск по дате, владельцу, тексту, тегам, сущностям.
Контракт /entities/search: has_more, score, match_type, search_mode дефолт.
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
        entities = resp.json()["items"]
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
        entities = resp.json()["items"]
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
        
        payload = search_resp.json()
        assert isinstance(payload, dict)
        assert "items" in payload
        assert isinstance(payload["items"], list)

    @pytest.mark.asyncio
    async def test_semantic_search_with_list_filters(self, crm_client, unique_id, auth_headers_system):
        """GET /entities/search принимает фильтры списка (status, entity_type) вместе с query."""
        await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": f"Semantic filter {unique_id}",
                "description": f"описание {unique_id}",
                "status": "active",
            },
            headers=auth_headers_system,
        )
        r = await crm_client.get(
            "/crm/api/v1/entities/search",
            params={
                "query": unique_id,
                "entity_type": "note",
                "status": "active",
                "limit": 50,
            },
            headers=auth_headers_system,
        )
        assert r.status_code == 200
        payload = r.json()
        assert isinstance(payload, dict)
        assert isinstance(payload["items"], list)
    
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
        entities = resp.json()["items"]
        found = [e for e in entities if unique_id in e.get("tags", [])]
        assert len(found) >= 1
    
    @pytest.mark.asyncio
    async def test_search_by_entity_name(self, crm_client, unique_id, auth_headers_system):
        """Список по типу находит entity по точному имени (/search — семантика, не подстрочное совпадение)."""
        unique_name = f"Уникальное_имя_{unique_id}"
        create_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": unique_name
        }, headers=auth_headers_system)
        assert create_resp.status_code == 200

        list_resp = await crm_client.get(
            "/crm/api/v1/entities/?entity_type=contact&limit=500",
            headers=auth_headers_system,
        )
        assert list_resp.status_code == 200
        found = [r for r in list_resp.json()["items"] if r["name"] == unique_name]
        assert len(found) >= 1


class TestSearchContract:
    """Контракт ответа /entities/search: score, match_type, has_more, search_mode дефолт."""

    @pytest.mark.asyncio
    async def test_search_has_more_always_false(self, crm_client, unique_id, auth_headers_system):
        """Поиск не поддерживает cursor-пагинацию: has_more=false."""
        await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "note", "name": f"has_more_check_{unique_id}"},
            headers=auth_headers_system,
        )
        for mode in ("hybrid", "text", "semantic"):
            resp = await crm_client.get(
                "/crm/api/v1/entities/search",
                params={"query": unique_id, "search_mode": mode, "limit": 1},
                headers=auth_headers_system,
            )
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["has_more"] is False, f"search_mode={mode}: has_more should be False"
            assert payload["next_cursor"] is None, f"search_mode={mode}: next_cursor should be None"

    @pytest.mark.asyncio
    async def test_search_default_mode_is_hybrid(self, crm_client, unique_id, auth_headers_system):
        """Без указания search_mode дефолт = hybrid."""
        await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": f"default_mode_{unique_id}",
                "description": f"text for search {unique_id}",
            },
            headers=auth_headers_system,
        )
        resp = await crm_client.get(
            "/crm/api/v1/entities/search",
            params={"query": unique_id},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        payload = resp.json()
        items = payload["items"]
        if items:
            item = items[0]
            assert "match_type" in item, "hybrid по умолчанию должен возвращать match_type"

    @pytest.mark.asyncio
    async def test_all_search_modes_return_score_and_match_type(
        self, crm_client, unique_id, auth_headers_system
    ):
        """Все три search_mode возвращают score и match_type (единый контракт)."""
        await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": f"score_contract_{unique_id}",
                "description": f"score contract description {unique_id}",
            },
            headers=auth_headers_system,
        )
        expected_match_types = {
            "hybrid": {"text", "semantic", "hybrid"},
            "text": {"text"},
            "semantic": {"semantic"},
        }
        for mode, valid_types in expected_match_types.items():
            resp = await crm_client.get(
                "/crm/api/v1/entities/search",
                params={"query": unique_id, "search_mode": mode, "limit": 50},
                headers=auth_headers_system,
            )
            assert resp.status_code == 200
            items = resp.json()["items"]
            for item in items:
                assert "score" in item, f"mode={mode}: score обязателен"
                assert "match_type" in item, f"mode={mode}: match_type обязателен"
                assert item["match_type"] in valid_types, (
                    f"mode={mode}: match_type={item['match_type']} не в {valid_types}"
                )

    @pytest.mark.asyncio
    async def test_mentions_search_accepts_namespace(self, crm_client, unique_id, auth_headers_system):
        """POST /entities/search/mentions принимает namespace."""
        await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "contact",
                "name": f"Mention_{unique_id}",
                "namespace": "default",
            },
            headers=auth_headers_system,
        )
        resp = await crm_client.post(
            "/crm/api/v1/entities/search/mentions",
            json={"text": f"Mention_{unique_id}", "namespace": "default"},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert isinstance(payload["entities"], list)

