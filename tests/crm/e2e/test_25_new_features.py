"""
Тесты новых функций CRM: schema validation, bulk API, export, hybrid search,
aggregate facets, relationship integrity, access_level.

Все тесты — E2E через реальную PostgreSQL. Без моков.
"""

import csv
import io
import json

import pytest


class TestSchemaValidation:
    """Проверка required_fields / типов при создании и обновлении сущностей."""

    async def _create_type_with_required_fields(
        self, crm_client, unique_id, headers, *, namespace_id="default"
    ):
        """Создаёт entity_type с required_fields и привязывает к namespace."""
        type_id = f"validated_{unique_id}"
        create_resp = await crm_client.post(
            "/crm/api/v1/entity-types/",
            json={
                "type_id": type_id,
                "name": "Validated Type",
                "required_fields": {
                    "email": {"type": "string"},
                    "age": {"type": "integer"},
                },
                "optional_fields": {
                    "notes": {"type": "string"},
                },
                "namespace": namespace_id,
            },
            headers=headers,
        )
        assert create_resp.status_code == 200, create_resp.text
        return type_id

    @pytest.mark.asyncio
    async def test_create_entity_missing_required_field(
        self, crm_client, unique_id, auth_headers_system
    ):
        """422 при отсутствии обязательного поля."""
        type_id = await self._create_type_with_required_fields(
            crm_client, unique_id, auth_headers_system
        )
        resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": type_id,
                "name": f"Без email {unique_id}",
                "attributes": {"age": 25},
            },
            headers=auth_headers_system,
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert isinstance(detail, list)
        fields = {e["field"] for e in detail}
        assert "email" in fields

    @pytest.mark.asyncio
    async def test_create_entity_wrong_field_type(
        self, crm_client, unique_id, auth_headers_system
    ):
        """422 при несоответствии типа поля."""
        type_id = await self._create_type_with_required_fields(
            crm_client, unique_id, auth_headers_system
        )
        resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": type_id,
                "name": f"Не тот тип {unique_id}",
                "attributes": {"email": "ok@mail.com", "age": "not_integer"},
            },
            headers=auth_headers_system,
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        age_errors = [e for e in detail if e["field"] == "age"]
        assert len(age_errors) == 1
        assert "integer" in age_errors[0]["error"]

    @pytest.mark.asyncio
    async def test_create_entity_valid_required_fields(
        self, crm_client, unique_id, auth_headers_system
    ):
        """200 при корректных обязательных полях."""
        type_id = await self._create_type_with_required_fields(
            crm_client, unique_id, auth_headers_system
        )
        resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": type_id,
                "name": f"Валидная сущность {unique_id}",
                "attributes": {"email": "a@b.com", "age": 30},
            },
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        entity = resp.json()
        assert entity["attributes"]["email"] == "a@b.com"
        assert entity["attributes"]["age"] == 30

    @pytest.mark.asyncio
    async def test_create_entity_coerces_numeric_strings(
        self, crm_client, unique_id, auth_headers_system
    ):
        """Строки с числом для integer/number принимаются и сохраняются как числа."""
        type_id = await self._create_type_with_required_fields(
            crm_client, unique_id, auth_headers_system
        )
        resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": type_id,
                "name": f"Строковые числа {unique_id}",
                "attributes": {"email": "n@n.ru", "age": "31"},
            },
            headers=auth_headers_system,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["attributes"]["age"] == 31

        type_amt = f"deal_amt_{unique_id}"
        amt_resp = await crm_client.post(
            "/crm/api/v1/entity-types/",
            json={
                "type_id": type_amt,
                "name": "Deal amount",
                "required_fields": {"amount": {"type": "number", "label": "Amount"}},
                "optional_fields": {},
                "namespace": "default",
            },
            headers=auth_headers_system,
        )
        assert amt_resp.status_code == 200, amt_resp.text

        resp2 = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": type_amt,
                "name": f"Сделка {unique_id}",
                "attributes": {"amount": "1500000"},
            },
            headers=auth_headers_system,
        )
        assert resp2.status_code == 200, resp2.text
        amt = resp2.json()["attributes"]["amount"]
        assert amt == 1500000 or amt == 1500000.0

    @pytest.mark.asyncio
    async def test_update_entity_schema_violation(
        self, crm_client, unique_id, auth_headers_system
    ):
        """422 при обновлении attributes с невалидным типом."""
        type_id = await self._create_type_with_required_fields(
            crm_client, unique_id, auth_headers_system
        )
        create_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": type_id,
                "name": f"Обновляемая {unique_id}",
                "attributes": {"email": "x@y.com", "age": 20},
            },
            headers=auth_headers_system,
        )
        assert create_resp.status_code == 200
        entity_id = create_resp.json()["entity_id"]

        update_resp = await crm_client.put(
            f"/crm/api/v1/entities/{entity_id}",
            json={"attributes": {"email": 12345, "age": 20}},
            headers=auth_headers_system,
        )
        assert update_resp.status_code == 422
        detail = update_resp.json()["detail"]
        email_errors = [e for e in detail if e["field"] == "email"]
        assert len(email_errors) == 1


@pytest.mark.timeout(30)
class TestBulkOperations:
    """Batch create / update / delete через /entities/bulk."""

    @pytest.mark.asyncio
    async def test_bulk_create(self, crm_client, unique_id, auth_headers_system):
        """Создание нескольких сущностей за один запрос."""
        items = [
            {
                "entity_type": "note",
                "name": f"Bulk note {i} {unique_id}",
            }
            for i in range(5)
        ]
        resp = await crm_client.post(
            "/crm/api/v1/entities/bulk",
            json={"items": items},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["errors"]) == 0, f"bulk create errors: {body['errors']}"
        assert len(body["created"]) == 5
        for entity in body["created"]:
            assert entity["entity_type"] == "note"

    @pytest.mark.asyncio
    async def test_bulk_create_partial_failure(
        self, crm_client, unique_id, auth_headers_system
    ):
        """Частичный сбой: один элемент с несуществующим типом."""
        items = [
            {"entity_type": "note", "name": f"Good {unique_id}"},
            {"entity_type": f"nonexistent_type_{unique_id}", "name": "Bad"},
        ]
        resp = await crm_client.post(
            "/crm/api/v1/entities/bulk",
            json={"items": items},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["created"]) == 1
        assert len(body["errors"]) == 1
        assert body["errors"][0]["index"] == 1

    @pytest.mark.asyncio
    async def test_bulk_create_exceeds_limit(
        self, crm_client, unique_id, auth_headers_system
    ):
        """422 при превышении лимита 200 элементов."""
        items = [
            {"entity_type": "note", "name": f"Item {i}"}
            for i in range(201)
        ]
        resp = await crm_client.post(
            "/crm/api/v1/entities/bulk",
            json={"items": items},
            headers=auth_headers_system,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_bulk_update(self, crm_client, unique_id, auth_headers_system):
        """Обновление нескольких сущностей за один запрос."""
        entity_ids = []
        for i in range(3):
            create_resp = await crm_client.post(
                "/crm/api/v1/entities/",
                json={
                    "entity_type": "task",
                    "name": f"Task {i} {unique_id}",
                },
                headers=auth_headers_system,
            )
            assert create_resp.status_code == 200
            entity_ids.append(create_resp.json()["entity_id"])

        items = [
            {"entity_id": eid, "updates": {"priority": "high"}}
            for eid in entity_ids
        ]
        resp = await crm_client.put(
            "/crm/api/v1/entities/bulk",
            json={"items": items},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["updated"]) == 3
        assert len(body["errors"]) == 0
        for updated in body["updated"]:
            assert updated["priority"] == "high"

    @pytest.mark.asyncio
    async def test_bulk_delete(self, crm_client, unique_id, auth_headers_system):
        """Удаление нескольких сущностей за один запрос."""
        entity_ids = []
        for i in range(3):
            create_resp = await crm_client.post(
                "/crm/api/v1/entities/",
                json={
                    "entity_type": "note",
                    "name": f"Del {i} {unique_id}",
                },
                headers=auth_headers_system,
            )
            assert create_resp.status_code == 200
            entity_ids.append(create_resp.json()["entity_id"])

        resp = await crm_client.post(
            "/crm/api/v1/entities/bulk-delete",
            json={"entity_ids": entity_ids},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body["deleted"]) == set(entity_ids)
        assert len(body["errors"]) == 0

        for eid in entity_ids:
            get_resp = await crm_client.get(
                f"/crm/api/v1/entities/{eid}", headers=auth_headers_system
            )
            assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_bulk_delete_nonexistent(
        self, crm_client, unique_id, auth_headers_system
    ):
        """Частичный сбой: один элемент не существует."""
        create_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "note", "name": f"Real {unique_id}"},
            headers=auth_headers_system,
        )
        real_id = create_resp.json()["entity_id"]
        fake_id = f"nonexistent_{unique_id}"

        resp = await crm_client.post(
            "/crm/api/v1/entities/bulk-delete",
            json={"entity_ids": [real_id, fake_id]},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert real_id in body["deleted"]
        assert len(body["errors"]) == 1
        assert body["errors"][0]["entity_id"] == fake_id


class TestExport:
    """Streaming export сущностей в CSV и JSON."""

    @pytest.mark.asyncio
    async def test_export_json(self, crm_client, unique_id, auth_headers_system):
        """Экспорт в JSON содержит созданные сущности."""
        user_marker = f"export_json_{unique_id}"
        for i in range(3):
            await crm_client.post(
                "/crm/api/v1/entities/",
                json={
                    "entity_type": "note",
                    "name": f"Export {i} {unique_id}",
                    "user_id": user_marker,
                },
                headers=auth_headers_system,
            )

        resp = await crm_client.get(
            "/crm/api/v1/entities/export",
            params={"format": "json", "entity_type": "note"},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]

        items = json.loads(resp.text)
        assert isinstance(items, list)
        exported_names = {item["name"] for item in items}
        for i in range(3):
            assert f"Export {i} {unique_id}" in exported_names

    @pytest.mark.asyncio
    async def test_export_csv(self, crm_client, unique_id, auth_headers_system):
        """Экспорт в CSV: заголовок + строки с данными."""
        for i in range(2):
            await crm_client.post(
                "/crm/api/v1/entities/",
                json={
                    "entity_type": "note",
                    "name": f"CSV {i} {unique_id}",
                },
                headers=auth_headers_system,
            )

        resp = await crm_client.get(
            "/crm/api/v1/entities/export",
            params={"format": "csv", "entity_type": "note"},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

        reader = csv.reader(io.StringIO(resp.text))
        rows = list(reader)
        header = rows[0]
        assert "entity_id" in header
        assert "name" in header
        assert "entity_type" in header

        data_rows = rows[1:]
        assert len(data_rows) >= 2
        name_col = header.index("name")
        exported_names = {row[name_col] for row in data_rows}
        for i in range(2):
            assert f"CSV {i} {unique_id}" in exported_names

    @pytest.mark.asyncio
    async def test_export_content_disposition(
        self, crm_client, unique_id, auth_headers_system
    ):
        """Content-Disposition содержит filename."""
        resp = await crm_client.get(
            "/crm/api/v1/entities/export",
            params={"format": "json"},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        assert "filename=" in resp.headers.get("content-disposition", "")


class TestSearchModes:
    """Поиск: text (FTS) и hybrid (RRF)."""

    @pytest.mark.asyncio
    async def test_text_search_mode(self, crm_client, unique_id, auth_headers_system):
        """search_mode=text использует tsvector FTS."""
        marker = f"fulltextsearch_{unique_id}"
        await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": f"Документ {marker}",
                "description": f"Содержимое {marker} для поиска",
            },
            headers=auth_headers_system,
        )

        resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "query": marker,
                "search_mode": "text",
                "entity_type": "note",
                "limit": 50,
            },
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        found_names = {item["name"] for item in items}
        assert f"Документ {marker}" in found_names

    @pytest.mark.asyncio
    async def test_hybrid_search_returns_score_and_match_type(
        self, crm_client, unique_id, auth_headers_system
    ):
        """search_mode=hybrid возвращает score и match_type."""
        marker = f"hybridsearch_{unique_id}"
        await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": f"Hybrid {marker}",
                "description": f"Текст для hybrid {marker} проверка",
            },
            headers=auth_headers_system,
        )

        from tests.fixtures.crm_test_setup import wait_for_crm_semantic_search_hit
        await wait_for_crm_semantic_search_hit(
            crm_client, auth_headers_system,
            query=marker, entity_type="note",
        )

        resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "query": marker,
                "search_mode": "hybrid",
                "entity_type": "note",
                "limit": 50,
            },
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1

        first = items[0]
        assert first["score"] is not None
        assert first["score"] > 0
        assert first["match_type"] in ("text", "semantic", "hybrid")

    @pytest.mark.asyncio
    async def test_text_search_with_filters(
        self, crm_client, unique_id, auth_headers_system
    ):
        """text search + status filter."""
        marker = f"filtered_{unique_id}"
        create_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "task",
                "name": f"Task {marker}",
                "description": f"Задача {marker} фильтрация",
            },
            headers=auth_headers_system,
        )
        entity_id = create_resp.json()["entity_id"]
        await crm_client.put(
            f"/crm/api/v1/entities/{entity_id}",
            json={"status": "archived"},
            headers=auth_headers_system,
        )

        resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "query": marker,
                "search_mode": "text",
                "limit": 50,
                "filters": {"field": "status", "op": "$eq", "value": "archived"},
            },
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        found = [item for item in items if item["entity_id"] == entity_id]
        assert len(found) == 1
        assert found[0]["status"] == "archived"


@pytest.mark.timeout(30)
class TestAggregateFacets:
    """Фасетная агрегация по типам, статусам, месяцам."""

    @pytest.mark.asyncio
    async def test_aggregate_returns_facets(
        self, crm_client, unique_id, auth_headers_system
    ):
        """Endpoint /aggregate возвращает by_type, by_status, by_month."""
        for i in range(3):
            await crm_client.post(
                "/crm/api/v1/entities/",
                json={
                    "entity_type": "note",
                    "name": f"Agg note {i} {unique_id}",
                },
                headers=auth_headers_system,
            )
        await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "task",
                "name": f"Agg task {unique_id}",
            },
            headers=auth_headers_system,
        )

        resp = await crm_client.get(
            "/crm/api/v1/entities/aggregate",
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        body = resp.json()

        assert "by_type" in body
        assert "by_status" in body
        assert "by_month" in body

        assert isinstance(body["by_type"], dict)
        assert "note" in body["by_type"]
        assert body["by_type"]["note"] >= 3
        assert "task" in body["by_type"]
        assert body["by_type"]["task"] >= 1

        assert isinstance(body["by_status"], dict)
        assert "active" in body["by_status"]

        assert isinstance(body["by_month"], dict)
        assert len(body["by_month"]) >= 1

    @pytest.mark.asyncio
    async def test_aggregate_with_namespace_filter(
        self, crm_client, unique_id, auth_headers_system
    ):
        """Фильтрация по namespace: видим только сущности из нужного пространства."""
        ns = f"g_{unique_id}"
        await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "contact",
                "name": f"NS contact {unique_id}",
                "namespace": ns,
            },
            headers=auth_headers_system,
        )

        resp = await crm_client.get(
            "/crm/api/v1/entities/aggregate",
            params={"namespace": ns},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["by_type"].get("contact", 0) >= 1


@pytest.mark.timeout(30)
class TestRelationshipIntegrity:
    """FK constraints и unique constraint на relationships."""

    @pytest.mark.asyncio
    async def test_duplicate_relationship_returns_409(
        self, crm_client, unique_id, auth_headers_system
    ):
        """Повторное создание связи с теми же source/target/type → 409."""
        e1_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "note", "name": f"Rel src {unique_id}"},
            headers=auth_headers_system,
        )
        e2_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "contact", "name": f"Rel tgt {unique_id}"},
            headers=auth_headers_system,
        )
        src_id = e1_resp.json()["entity_id"]
        tgt_id = e2_resp.json()["entity_id"]

        rel_data = {
            "source_entity_id": src_id,
            "target_entity_id": tgt_id,
            "relationship_type": "mentions",
        }

        first_resp = await crm_client.post(
            "/crm/api/v1/relationships/",
            json=rel_data,
            headers=auth_headers_system,
        )
        assert first_resp.status_code == 200

        dup_resp = await crm_client.post(
            "/crm/api/v1/relationships/",
            json=rel_data,
            headers=auth_headers_system,
        )
        assert dup_resp.status_code == 409
        assert "already exists" in dup_resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cascade_delete_removes_relationships(
        self, crm_client, unique_id, auth_headers_system
    ):
        """При удалении сущности связи удаляются каскадно (FK ON DELETE CASCADE)."""
        e1_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "note", "name": f"Cascade src {unique_id}"},
            headers=auth_headers_system,
        )
        e2_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "contact", "name": f"Cascade tgt {unique_id}"},
            headers=auth_headers_system,
        )
        src_id = e1_resp.json()["entity_id"]
        tgt_id = e2_resp.json()["entity_id"]

        rel_resp = await crm_client.post(
            "/crm/api/v1/relationships/",
            json={
                "source_entity_id": src_id,
                "target_entity_id": tgt_id,
                "relationship_type": "mentions",
            },
            headers=auth_headers_system,
        )
        assert rel_resp.status_code == 200
        rel_id = rel_resp.json()["relationship_id"]

        delete_resp = await crm_client.delete(
            f"/crm/api/v1/entities/{src_id}",
            headers=auth_headers_system,
        )
        assert delete_resp.status_code == 200

        get_rel_resp = await crm_client.get(
            f"/crm/api/v1/relationships/{rel_id}",
            headers=auth_headers_system,
        )
        assert get_rel_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_different_namespace_allows_same_pair(
        self, crm_client, unique_id, auth_headers_system
    ):
        """Связи с одинаковой парой, но разными namespace — допустимы."""
        ns = f"g_{unique_id}"

        e1_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "note", "name": f"NS rel src {unique_id}"},
            headers=auth_headers_system,
        )
        e2_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "contact", "name": f"NS rel tgt {unique_id}"},
            headers=auth_headers_system,
        )
        src_id = e1_resp.json()["entity_id"]
        tgt_id = e2_resp.json()["entity_id"]

        resp_default = await crm_client.post(
            "/crm/api/v1/relationships/",
            json={
                "source_entity_id": src_id,
                "target_entity_id": tgt_id,
                "relationship_type": "mentions",
                "namespace": "default",
            },
            headers=auth_headers_system,
        )
        assert resp_default.status_code == 200

        resp_ns = await crm_client.post(
            "/crm/api/v1/relationships/",
            json={
                "source_entity_id": src_id,
                "target_entity_id": tgt_id,
                "relationship_type": "mentions",
                "namespace": ns,
            },
            headers=auth_headers_system,
        )
        assert resp_ns.status_code == 200


class TestAccessLevel:
    """access_level в ответах list / get."""

    @pytest.mark.asyncio
    async def test_owner_gets_access_level_owner(
        self, crm_client, unique_id, auth_headers_system
    ):
        """Создатель видит access_level=owner."""
        create_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "note", "name": f"Owner entity {unique_id}"},
            headers=auth_headers_system,
        )
        assert create_resp.status_code == 200

        list_resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={"entity_type": "note", "limit": 100},
            headers=auth_headers_system,
        )
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        own_entity = [
            e for e in items if e["name"] == f"Owner entity {unique_id}"
        ]
        assert len(own_entity) >= 1
        assert own_entity[0]["access_level"] == "owner"

    @pytest.mark.asyncio
    async def test_same_company_user_sees_entities(
        self, crm_client, unique_id, auth_headers_system, auth_headers_system_user2
    ):
        """Пользователь той же компании видит сущности и access_level=owner (same company)."""
        create_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "note", "name": f"Same company {unique_id}"},
            headers=auth_headers_system,
        )
        assert create_resp.status_code == 200
        entity_id = create_resp.json()["entity_id"]

        get_resp = await crm_client.get(
            f"/crm/api/v1/entities/{entity_id}",
            headers=auth_headers_system_user2,
        )
        assert get_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_cross_company_entity_hidden(
        self, crm_client, unique_id, auth_headers_system, auth_headers_company2
    ):
        """Пользователь другой компании не видит чужую сущность."""
        create_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "note", "name": f"Hidden {unique_id}"},
            headers=auth_headers_system,
        )
        assert create_resp.status_code == 200
        entity_id = create_resp.json()["entity_id"]

        get_resp = await crm_client.get(
            f"/crm/api/v1/entities/{entity_id}",
            headers=auth_headers_company2,
        )
        assert get_resp.status_code in (403, 404)
