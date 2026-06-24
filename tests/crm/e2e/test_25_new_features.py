"""
Тесты новых функций CRM: schema validation, bulk API, export, hybrid search,
aggregate facets, relationship integrity, access_level.

Все тесты — E2E через реальную PostgreSQL. Без моков.
"""

import csv
import io
import json
from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_dict, object_list, object_str

pytestmark = pytest.mark.timeout(120, func_only=True)


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _entity_id(response: Response) -> str:
    return object_str(_http_json(response).get("entity_id"), field="entity_id")


def _relationship_id(response: Response) -> str:
    return object_str(_http_json(response).get("relationship_id"), field="relationship_id")


def _query_items(response: Response) -> list[dict[str, object]]:
    return object_list(_http_json(response).get("items"))


def _validation_errors(response: Response) -> list[dict[str, object]]:
    return object_list(_http_json(response).get("detail"))


def _attributes(entity: dict[str, object]) -> dict[str, object]:
    return object_dict(entity.get("attributes"), field="attributes")


def _bulk_body(response: Response) -> dict[str, object]:
    return _http_json(response)


def _bulk_created_entities(response: Response) -> list[dict[str, object]]:
    return object_list(_bulk_body(response).get("created"))


def _bulk_updated_entities(response: Response) -> list[dict[str, object]]:
    return object_list(_bulk_body(response).get("updated"))


def _bulk_error_entries(response: Response) -> list[dict[str, object]]:
    return object_list(_bulk_body(response).get("errors"))


def _bulk_deleted_ids(response: Response) -> list[str]:
    return _string_list(_bulk_body(response).get("deleted"))


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


def _facet_counts(facets: dict[str, object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, value in facets.items():
        if isinstance(value, int):
            counts[key] = value
    return counts


def _export_json_items(text: str) -> list[dict[str, object]]:
    return object_list(cast(object, json.loads(text)))


def _detail_text(response: Response) -> str:
    detail = _http_json(response).get("detail")
    if isinstance(detail, str):
        return detail
    return str(detail)


def _entity_names(items: list[dict[str, object]]) -> set[str]:
    return {object_str(item.get("name"), field="name") for item in items}


def _error_index(error_entry: dict[str, object]) -> int:
    index = error_entry.get("index")
    if not isinstance(index, int):
        raise AssertionError("index must be an int")
    return index


def _numeric_value(value: object, *, field: str) -> float:
    if not isinstance(value, (int, float)):
        raise AssertionError(f"{field} must be a number")
    return float(value)


class TestSchemaValidation:
    """Проверка required_fields / типов при создании и обновлении сущностей."""

    async def _create_type_with_required_fields(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        headers: dict[str, str],
        *,
        namespace_id: str = "default",
    ) -> str:
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
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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
        detail = _validation_errors(resp)
        fields = {object_str(entry.get("field"), field="field") for entry in detail}
        assert "email" in fields

    @pytest.mark.asyncio
    async def test_create_entity_wrong_field_type(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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
        detail = _validation_errors(resp)
        age_errors = [
            entry
            for entry in detail
            if object_str(entry.get("field"), field="field") == "age"
        ]
        assert len(age_errors) == 1
        error_message = object_str(age_errors[0].get("error"), field="error")
        assert "integer" in error_message

    @pytest.mark.asyncio
    async def test_create_entity_valid_required_fields(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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
        entity = _http_json(resp)
        attributes = _attributes(entity)
        assert object_str(attributes.get("email"), field="email") == "a@b.com"
        assert _int_field(attributes, "age") == 30

    @pytest.mark.asyncio
    async def test_create_entity_coerces_numeric_strings(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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
        assert _int_field(_attributes(_http_json(resp)), "age") == 31

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
        amt = _numeric_value(_attributes(_http_json(resp2)).get("amount"), field="amount")
        assert amt == 1500000.0

    @pytest.mark.asyncio
    async def test_update_entity_schema_violation(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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
        entity_id = _entity_id(create_resp)

        update_resp = await crm_client.put(
            f"/crm/api/v1/entities/{entity_id}",
            json={"attributes": {"email": 12345, "age": 20}},
            headers=auth_headers_system,
        )
        assert update_resp.status_code == 422
        detail = _validation_errors(update_resp)
        email_errors = [
            entry
            for entry in detail
            if object_str(entry.get("field"), field="field") == "email"
        ]
        assert len(email_errors) == 1


@pytest.mark.timeout(30)
class TestBulkOperations:
    """Batch create / update / delete через /entities/bulk."""

    @pytest.mark.asyncio
    async def test_bulk_create(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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
        errors = _bulk_error_entries(resp)
        assert len(errors) == 0, f"bulk create errors: {errors}"
        created = _bulk_created_entities(resp)
        assert len(created) == 5
        for entity in created:
            assert object_str(entity.get("entity_type"), field="entity_type") == "note"

    @pytest.mark.asyncio
    async def test_bulk_create_partial_failure(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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
        assert len(_bulk_created_entities(resp)) == 1
        error_entries = _bulk_error_entries(resp)
        assert len(error_entries) == 1
        assert _error_index(error_entries[0]) == 1

    @pytest.mark.asyncio
    async def test_bulk_create_exceeds_limit(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """422 при превышении лимита 200 элементов."""
        _ = unique_id
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
    async def test_bulk_update(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Обновление нескольких сущностей за один запрос."""
        entity_ids: list[str] = []
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
            entity_ids.append(_entity_id(create_resp))

        items = [
            {"entity_id": eid, "updates": {"status": "completed"}}
            for eid in entity_ids
        ]
        resp = await crm_client.put(
            "/crm/api/v1/entities/bulk",
            json={"items": items},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        updated = _bulk_updated_entities(resp)
        assert len(updated) == 3
        assert len(_bulk_error_entries(resp)) == 0
        for updated_entity in updated:
            assert object_str(updated_entity.get("status"), field="status") == "completed"

    @pytest.mark.asyncio
    async def test_bulk_delete(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Удаление нескольких сущностей за один запрос."""
        entity_ids: list[str] = []
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
            entity_ids.append(_entity_id(create_resp))

        resp = await crm_client.post(
            "/crm/api/v1/entities/bulk-delete",
            json={"entity_ids": entity_ids},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        deleted_ids = _bulk_deleted_ids(resp)
        assert set(deleted_ids) == set(entity_ids)
        assert len(_bulk_error_entries(resp)) == 0

        for eid in entity_ids:
            get_resp = await crm_client.get(
                f"/crm/api/v1/entities/{eid}", headers=auth_headers_system
            )
            assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_bulk_delete_nonexistent(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Частичный сбой: один элемент не существует."""
        create_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "note", "name": f"Real {unique_id}"},
            headers=auth_headers_system,
        )
        real_id = _entity_id(create_resp)
        fake_id = f"nonexistent_{unique_id}"

        resp = await crm_client.post(
            "/crm/api/v1/entities/bulk-delete",
            json={"entity_ids": [real_id, fake_id]},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        deleted_ids = _bulk_deleted_ids(resp)
        assert real_id in deleted_ids
        error_entries = _bulk_error_entries(resp)
        assert len(error_entries) == 1
        assert object_str(error_entries[0].get("entity_id"), field="entity_id") == fake_id


class TestExport:
    """Streaming export сущностей в CSV и JSON."""

    @pytest.mark.asyncio
    async def test_export_json(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Экспорт в JSON содержит созданные сущности."""
        user_marker = f"export_json_{unique_id}"
        for i in range(3):
            _ = await crm_client.post(
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

        items = _export_json_items(resp.text)
        exported_names = _entity_names(items)
        for i in range(3):
            assert f"Export {i} {unique_id}" in exported_names

    @pytest.mark.asyncio
    async def test_export_csv(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Экспорт в CSV: заголовок + строки с данными."""
        for i in range(2):
            _ = await crm_client.post(
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
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Content-Disposition содержит filename."""
        _ = unique_id
        resp = await crm_client.get(
            "/crm/api/v1/entities/export",
            params={"format": "json"},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        raw_disposition = cast(object, resp.headers.get("content-disposition"))
        content_disposition = raw_disposition if isinstance(raw_disposition, str) else ""
        assert "filename=" in content_disposition


class TestSearchModes:
    """Поиск: text (FTS) и hybrid (RRF)."""

    @pytest.mark.asyncio
    async def test_text_search_mode(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """search_mode=text использует tsvector FTS."""
        marker = f"fulltextsearch_{unique_id}"
        _ = await crm_client.post(
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
        found_names = _entity_names(_query_items(resp))
        assert f"Документ {marker}" in found_names

    @pytest.mark.asyncio
    async def test_hybrid_search_returns_score_and_match_type(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """search_mode=hybrid возвращает score и match_type."""
        marker = f"hybridsearch_{unique_id}"
        _ = await crm_client.post(
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
        items = _query_items(resp)
        assert len(items) >= 1

        first = items[0]
        score = first.get("score")
        if score is None:
            raise AssertionError("score must be present")
        assert _numeric_value(score, field="score") > 0
        match_type = object_str(first.get("match_type"), field="match_type")
        assert match_type in ("text", "semantic", "hybrid")

    @pytest.mark.asyncio
    async def test_text_search_with_filters(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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
        entity_id = _entity_id(create_resp)
        _ = await crm_client.put(
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
        found = [
            item
            for item in _query_items(resp)
            if object_str(item.get("entity_id"), field="entity_id") == entity_id
        ]
        assert len(found) == 1
        assert object_str(found[0].get("status"), field="status") == "archived"


@pytest.mark.timeout(30)
class TestAggregateFacets:
    """Фасетная агрегация по типам, статусам, месяцам."""

    @pytest.mark.asyncio
    async def test_aggregate_returns_facets(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Endpoint /aggregate возвращает by_type, by_status, by_month."""
        for i in range(3):
            _ = await crm_client.post(
                "/crm/api/v1/entities/",
                json={
                    "entity_type": "note",
                    "name": f"Agg note {i} {unique_id}",
                },
                headers=auth_headers_system,
            )
        _ = await crm_client.post(
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
        body = _http_json(resp)

        by_type = _facet_counts(object_dict(body.get("by_type"), field="by_type"))
        by_status = _facet_counts(object_dict(body.get("by_status"), field="by_status"))
        by_month = _facet_counts(object_dict(body.get("by_month"), field="by_month"))

        assert "note" in by_type
        assert by_type["note"] >= 3
        assert "task" in by_type
        assert by_type["task"] >= 1

        assert "active" in by_status

        assert len(by_month) >= 1

    @pytest.mark.asyncio
    async def test_aggregate_with_namespace_filter(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Фильтрация по namespace: видим только сущности из нужного пространства."""
        ns = f"g_{unique_id}"
        _ = await crm_client.post(
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
        body = _http_json(resp)
        by_type = _facet_counts(object_dict(body.get("by_type"), field="by_type"))
        assert by_type.get("contact", 0) >= 1


@pytest.mark.timeout(30)
class TestRelationshipIntegrity:
    """FK constraints и unique constraint на relationships."""

    @pytest.mark.asyncio
    async def test_duplicate_relationship_returns_409(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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
        src_id = _entity_id(e1_resp)
        tgt_id = _entity_id(e2_resp)

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
        assert "already exists" in _detail_text(dup_resp).lower()

    @pytest.mark.asyncio
    async def test_cascade_delete_removes_relationships(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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
        src_id = _entity_id(e1_resp)
        tgt_id = _entity_id(e2_resp)

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
        rel_id = _relationship_id(rel_resp)

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
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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
        src_id = _entity_id(e1_resp)
        tgt_id = _entity_id(e2_resp)

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
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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
        own_entity = [
            entity
            for entity in _query_items(list_resp)
            if object_str(entity.get("name"), field="name") == f"Owner entity {unique_id}"
        ]
        assert len(own_entity) >= 1
        assert object_str(own_entity[0].get("access_level"), field="access_level") == "owner"

    @pytest.mark.asyncio
    async def test_same_company_user_sees_entities(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
        auth_headers_system_user2: dict[str, str],
    ) -> None:
        """Пользователь той же компании видит сущности и access_level=owner (same company)."""
        create_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "note", "name": f"Same company {unique_id}"},
            headers=auth_headers_system,
        )
        assert create_resp.status_code == 200
        entity_id = _entity_id(create_resp)

        get_resp = await crm_client.get(
            f"/crm/api/v1/entities/{entity_id}",
            headers=auth_headers_system_user2,
        )
        assert get_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_cross_company_entity_hidden(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
        auth_headers_company2: dict[str, str],
    ) -> None:
        """Пользователь другой компании не видит чужую сущность."""
        create_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "note", "name": f"Hidden {unique_id}"},
            headers=auth_headers_system,
        )
        assert create_resp.status_code == 200
        entity_id = _entity_id(create_resp)

        get_resp = await crm_client.get(
            f"/crm/api/v1/entities/{entity_id}",
            headers=auth_headers_company2,
        )
        assert get_resp.status_code in (403, 404)
