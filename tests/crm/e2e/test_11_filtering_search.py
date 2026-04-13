"""Тесты DSL-фильтрации и поиска через POST /entities/query."""

from datetime import date

import pytest


class TestFilteringSearch:
    @staticmethod
    async def _create_typed_entities_for_filters(crm_client, unique_id, headers) -> str:
        type_id = f"typed_filters_{unique_id}"
        create_type = await crm_client.post(
            "/crm/api/v1/entity-types",
            json={
                "type_id": type_id,
                "name": f"Typed Filters {unique_id}",
                "required_fields": {},
                "optional_fields": {
                    "environment": {"type": "string"},
                    "estimate_hours": {"type": "integer"},
                    "progress_ratio": {"type": "number"},
                    "done": {"type": "boolean"},
                    "release_date": {"type": "date"},
                    "release_at": {"type": "datetime"},
                    "labels": {"type": "array"},
                },
            },
            headers=headers,
        )
        assert create_type.status_code == 200

        create_first = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": type_id,
                "name": f"Typed A {unique_id}",
                "attributes": {
                    "environment": "prod",
                    "estimate_hours": 12,
                    "progress_ratio": 0.85,
                    "done": True,
                    "release_date": "2026-01-10",
                    "release_at": "2026-01-10T11:30:00Z",
                    "labels": ["urgent", "vip"],
                },
            },
            headers=headers,
        )
        assert create_first.status_code == 200

        create_second = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": type_id,
                "name": f"Typed B {unique_id}",
                "attributes": {
                    "environment": "stage",
                    "estimate_hours": 3,
                    "progress_ratio": 0.2,
                    "done": False,
                    "release_date": "2026-03-20",
                    "release_at": "2026-03-20T08:00:00Z",
                    "labels": ["backlog"],
                },
            },
            headers=headers,
        )
        assert create_second.status_code == 200
        return type_id

    @pytest.mark.asyncio
    async def test_query_filters_by_note_date_and_user(self, crm_client, unique_id, auth_headers_system):
        today = date.today().isoformat()
        test_user_id = f"user_{unique_id}"
        await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": f"Note {unique_id}",
                "note_date": today,
                "user_id": test_user_id,
            },
            headers=auth_headers_system,
        )

        response = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": "note",
                "limit": 100,
                "filters": {
                    "$and": [
                        {"field": "note_date", "op": "$eq", "value": today},
                        {"field": "user_id", "op": "$eq", "value": test_user_id},
                    ]
                },
            },
            headers=auth_headers_system,
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert any(item["user_id"] == test_user_id for item in items)

    @pytest.mark.asyncio
    async def test_query_filters_attributes_with_type_safe_ops(self, crm_client, unique_id, auth_headers_system):
        type_id = f"typed_task_{unique_id}"
        create_type = await crm_client.post(
            "/crm/api/v1/entity-types",
            json={
                "type_id": type_id,
                "name": f"Typed Task {unique_id}",
                "required_fields": {},
                "optional_fields": {
                    "estimate_hours": {"type": "integer", "label": "Estimate"},
                    "environment": {"type": "string", "label": "Environment"},
                },
            },
            headers=auth_headers_system,
        )
        assert create_type.status_code == 200

        await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": type_id,
                "name": f"Task {unique_id}",
                "attributes": {"estimate_hours": 8, "environment": "prod"},
            },
            headers=auth_headers_system,
        )
        await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": type_id,
                "name": f"Task low {unique_id}",
                "attributes": {"estimate_hours": 2, "environment": "dev"},
            },
            headers=auth_headers_system,
        )

        response = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": type_id,
                "filters": {
                    "$and": [
                        {"field": "attributes.estimate_hours", "op": "$gte", "value": 5},
                        {"field": "attributes.environment", "op": "$eq", "value": "prod"},
                    ]
                },
            },
            headers=auth_headers_system,
        )
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["items"]) >= 1
        assert all(item["attributes"]["estimate_hours"] >= 5 for item in payload["items"])

    @pytest.mark.asyncio
    async def test_query_rejects_invalid_operator_for_field_type(
        self, crm_client, unique_id, auth_headers_system
    ):
        type_id = f"typed_bool_{unique_id}"
        create_type = await crm_client.post(
            "/crm/api/v1/entity-types",
            json={
                "type_id": type_id,
                "name": f"Typed Bool {unique_id}",
                "required_fields": {},
                "optional_fields": {
                    "done": {"type": "boolean", "label": "Done"},
                },
            },
            headers=auth_headers_system,
        )
        assert create_type.status_code == 200

        await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": type_id, "name": f"Task invalid op {unique_id}", "attributes": {"done": True}},
            headers=auth_headers_system,
        )
        response = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": type_id,
                "filters": {"field": "attributes.done", "op": "$contains", "value": True},
            },
            headers=auth_headers_system,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_query_nested_logical_filters_with_date_and_datetime(
        self, crm_client, unique_id, auth_headers_system
    ):
        type_id = await self._create_typed_entities_for_filters(crm_client, unique_id, auth_headers_system)
        response = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": type_id,
                "limit": 50,
                "filters": {
                    "$and": [
                        {
                            "$or": [
                                {"field": "attributes.environment", "op": "$eq", "value": "prod"},
                                {"field": "attributes.environment", "op": "$eq", "value": "dev"},
                            ]
                        },
                        {"field": "attributes.release_date", "op": "$lte", "value": "2026-01-31"},
                        {"field": "attributes.release_at", "op": "$lt", "value": "2026-02-01T00:00:00Z"},
                    ]
                },
            },
            headers=auth_headers_system,
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["attributes"]["environment"] == "prod"

    @pytest.mark.asyncio
    async def test_query_in_nin_and_contains_for_typed_fields(self, crm_client, unique_id, auth_headers_system):
        type_id = await self._create_typed_entities_for_filters(crm_client, unique_id, auth_headers_system)
        in_resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": type_id,
                "filters": {"field": "attributes.environment", "op": "$in", "value": ["prod", "qa"]},
            },
            headers=auth_headers_system,
        )
        assert in_resp.status_code == 200
        assert len(in_resp.json()["items"]) == 1

        nin_resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": type_id,
                "filters": {"field": "attributes.environment", "op": "$nin", "value": ["stage"]},
            },
            headers=auth_headers_system,
        )
        assert nin_resp.status_code == 200
        assert len(nin_resp.json()["items"]) == 1

        contains_resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": type_id,
                "filters": {"field": "attributes.labels", "op": "$contains", "value": "urgent"},
            },
            headers=auth_headers_system,
        )
        assert contains_resp.status_code == 200
        contains_items = contains_resp.json()["items"]
        assert len(contains_items) == 1
        assert "urgent" in contains_items[0]["attributes"]["labels"]

    @pytest.mark.asyncio
    async def test_query_rejects_invalid_filter_node_shape(self, crm_client, auth_headers_system):
        response = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": "note",
                "filters": {
                    "$and": [{"field": "status", "op": "$eq", "value": "active"}],
                    "$or": [{"field": "status", "op": "$eq", "value": "archived"}],
                },
            },
            headers=auth_headers_system,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_query_rejects_attributes_filter_without_entity_type(self, crm_client, auth_headers_system):
        response = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "filters": {"field": "attributes.environment", "op": "$eq", "value": "prod"},
            },
            headers=auth_headers_system,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_query_rejects_invalid_value_type_for_in(self, crm_client, unique_id, auth_headers_system):
        type_id = f"typed_validation_{unique_id}"
        create_type = await crm_client.post(
            "/crm/api/v1/entity-types",
            json={
                "type_id": type_id,
                "name": f"Typed Validation {unique_id}",
                "required_fields": {},
                "optional_fields": {"estimate_hours": {"type": "integer"}},
            },
            headers=auth_headers_system,
        )
        assert create_type.status_code == 200

        response = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": type_id,
                "filters": {"field": "attributes.estimate_hours", "op": "$in", "value": [1, "two"]},
            },
            headers=auth_headers_system,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_legacy_query_endpoints_disabled(self, crm_client, auth_headers_system):
        list_resp = await crm_client.get("/crm/api/v1/entities", headers=auth_headers_system)
        search_resp = await crm_client.get(
            "/crm/api/v1/entities/search",
            params={"query": "x"},
            headers=auth_headers_system,
        )
        assert list_resp.status_code == 410
        assert search_resp.status_code == 410


class TestSearchContract:
    @pytest.mark.asyncio
    async def test_query_search_modes_return_score_and_match_type(
        self, crm_client, unique_id, auth_headers_system
    ):
        await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": f"Search {unique_id}",
                "description": f"Score payload {unique_id}",
            },
            headers=auth_headers_system,
        )
        for mode in ("hybrid", "text", "semantic"):
            response = await crm_client.post(
                "/crm/api/v1/entities/query",
                json={"query": unique_id, "search_mode": mode, "limit": 20},
                headers=auth_headers_system,
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["has_more"] is False
            assert payload["next_cursor"] is None
            for item in payload["items"]:
                assert "score" in item
                assert "match_type" in item

    @pytest.mark.asyncio
    async def test_mentions_search_accepts_namespace(self, crm_client, unique_id, auth_headers_system):
        await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "contact", "name": f"Mention_{unique_id}", "namespace": "default"},
            headers=auth_headers_system,
        )
        response = await crm_client.post(
            "/crm/api/v1/entities/search/mentions",
            json={"text": f"Mention_{unique_id}", "namespace": "default"},
            headers=auth_headers_system,
        )
        assert response.status_code == 200
        assert isinstance(response.json()["entities"], list)

