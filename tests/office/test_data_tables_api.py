"""Office BFF: DataTable FileRecord create/page/mutate via MinIO."""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pytest
from httpx import AsyncClient, Response
from openpyxl import Workbook

from core.data_tables.import_tabular import parse_tabular_bytes
from core.data_tables.models import DATA_TABLE_CONTENT_TYPE
from tests.fixtures.s3 import require_s3_configured

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(120)]

_SQLITE_MAGIC = b"SQLite format 3"
_ALL_TYPED_COLUMNS: list[dict[str, str]] = [
    {"name": "title", "column_type": "text"},
    {"name": "score", "column_type": "integer"},
    {"name": "ratio", "column_type": "real"},
    {"name": "flag", "column_type": "boolean"},
    {"name": "seen_at", "column_type": "datetime"},
    {"name": "meta", "column_type": "json"},
    {"name": "doc", "column_type": "file_ref"},
]


async def _create_data_table(
    office_client: AsyncClient,
    auth_headers_system: dict[str, str],
    *,
    original_name: str,
    tables: list[dict[str, Any]],
) -> str:
    create_response = await office_client.post(
        "/documents/api/v1/data-tables",
        headers=auth_headers_system,
        json={
            "original_name": original_name,
            "scope": "office_document",
            "tables": tables,
        },
    )
    assert create_response.status_code == 200, create_response.text
    created = create_response.json()
    assert created["content_type"] == DATA_TABLE_CONTENT_TYPE
    file_id = created["file_id"]
    assert isinstance(file_id, str)
    assert file_id != ""
    return file_id


async def _page_items(
    office_client: AsyncClient,
    auth_headers_system: dict[str, str],
    file_id: str,
    table_name: str,
    *,
    limit: int = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    params: dict[str, str | int] = {"limit": limit}
    if cursor is not None:
        params["cursor"] = cursor
    page_response = await office_client.get(
        f"/documents/api/v1/data-tables/{file_id}/tables/{table_name}/rows",
        headers=auth_headers_system,
        params=params,
    )
    assert page_response.status_code == 200, page_response.text
    body = page_response.json()
    assert isinstance(body["items"], list)
    assert isinstance(body["has_more"], bool)
    return body


async def _patch_row(
    office_client: AsyncClient,
    auth_headers_system: dict[str, str],
    file_id: str,
    table_name: str,
    row_id: int,
    values: dict[str, Any],
) -> Response:
    return await office_client.patch(
        f"/documents/api/v1/data-tables/{file_id}/tables/{table_name}/rows/{row_id}",
        headers=auth_headers_system,
        json={"values": values},
    )


def _assert_user_export(payload: bytes, *, source_format: str, columns: list[str]) -> None:
    assert not payload.startswith(_SQLITE_MAGIC)
    assert _SQLITE_MAGIC not in payload[:64]
    parsed_columns, parsed_rows = parse_tabular_bytes(payload, source_format=source_format)
    assert [column.name for column in parsed_columns] == columns
    assert "row_id" not in columns
    assert all(column.name != "row_id" for column in parsed_columns)
    assert parsed_rows != []
    assert "row_id" not in parsed_rows[0]


async def test_data_table_create_page_and_cell_patch(
    office_client,
    auth_headers_system,
    unique_id: str,
) -> None:
    require_s3_configured()
    original_name = f"leads-{unique_id}.sqlite"
    create_response = await office_client.post(
        "/documents/api/v1/data-tables",
        headers=auth_headers_system,
        json={
            "original_name": original_name,
            "scope": "office_document",
            "tables": [
                {
                    "name": "leads",
                    "columns": [
                        {"name": "name", "column_type": "text"},
                        {"name": "score", "column_type": "integer"},
                    ],
                }
            ],
        },
    )
    assert create_response.status_code == 200, create_response.text
    created = create_response.json()
    file_id = created["file_id"]
    assert created["original_name"] == original_name
    assert created["content_type"] == DATA_TABLE_CONTENT_TYPE

    snapshot_response = await office_client.get(
        f"/documents/api/v1/data-tables/{file_id}",
        headers=auth_headers_system,
    )
    assert snapshot_response.status_code == 200, snapshot_response.text
    snapshot = snapshot_response.json()
    assert snapshot["schema_snapshot"]["tables"][0]["name"] == "leads"

    insert_response = await office_client.post(
        f"/documents/api/v1/data-tables/{file_id}/tables/leads/rows",
        headers=auth_headers_system,
        json={"rows": [{"name": "Ada", "score": 10}]},
    )
    assert insert_response.status_code == 200, insert_response.text
    row_ids = insert_response.json()["row_ids"]
    assert len(row_ids) == 1
    row_id = row_ids[0]

    page_response = await office_client.get(
        f"/documents/api/v1/data-tables/{file_id}/tables/leads/rows",
        headers=auth_headers_system,
        params={"limit": 50},
    )
    assert page_response.status_code == 200, page_response.text
    page = page_response.json()
    assert page["has_more"] is False
    assert page["items"][0]["values"]["name"] == "Ada"

    search_response = await office_client.get(
        f"/documents/api/v1/data-tables/{file_id}/tables/leads/rows",
        headers=auth_headers_system,
        params={"limit": 50, "q": "Ada"},
    )
    assert search_response.status_code == 200, search_response.text
    search_page = search_response.json()
    assert len(search_page["items"]) == 1
    assert search_page["items"][0]["values"]["name"] == "Ada"

    miss_response = await office_client.get(
        f"/documents/api/v1/data-tables/{file_id}/tables/leads/rows",
        headers=auth_headers_system,
        params={"limit": 50, "q": "NoSuchName"},
    )
    assert miss_response.status_code == 200, miss_response.text
    assert miss_response.json()["items"] == []

    column_q_response = await office_client.get(
        f"/documents/api/v1/data-tables/{file_id}/tables/leads/rows",
        headers=auth_headers_system,
        params={"limit": 50, "column_q": ["name:Ada"]},
    )
    assert column_q_response.status_code == 200, column_q_response.text
    column_q_page = column_q_response.json()
    assert len(column_q_page["items"]) == 1
    assert column_q_page["items"][0]["values"]["name"] == "Ada"

    column_q_miss = await office_client.get(
        f"/documents/api/v1/data-tables/{file_id}/tables/leads/rows",
        headers=auth_headers_system,
        params={"limit": 50, "column_q": ["name:NoSuchName"]},
    )
    assert column_q_miss.status_code == 200, column_q_miss.text
    assert column_q_miss.json()["items"] == []

    patch_response = await office_client.patch(
        f"/documents/api/v1/data-tables/{file_id}/tables/leads/rows/{row_id}",
        headers=auth_headers_system,
        json={"values": {"score": 42}},
    )
    assert patch_response.status_code == 200, patch_response.text

    query_response = await office_client.post(
        f"/documents/api/v1/data-tables/{file_id}/query",
        headers=auth_headers_system,
        json={"sql": "SELECT name, score FROM leads"},
    )
    assert query_response.status_code == 200, query_response.text
    query_body = query_response.json()
    assert query_body["columns"] == ["name", "score"]
    assert query_body["rows"][0][1] == 42

    editor_response = await office_client.get(
        f"/documents/api/v1/files/{file_id}/editor-config",
        headers=auth_headers_system,
    )
    assert editor_response.status_code == 200, editor_response.text
    editor = editor_response.json()
    assert editor["handler"] == "data_table"
    assert editor["capabilities"]["edit"] is True
    assert editor["capabilities"]["server_mutations"] is True
    assert editor["capabilities"]["sync_on_close"] is False
    assert editor["data_table"]["file_id"] == file_id
    assert editor["data_table"]["scope"] == "office_document"
    assert editor["data_table"]["rows_url"].startswith("/documents/api/v1/data-tables/")
    assert editor["data_table"]["mutate_url"].startswith("/documents/api/v1/data-tables/")
    download_url = editor["download_url"]
    assert isinstance(download_url, str)
    assert download_url.startswith("http")
    assert "host.docker.internal" not in download_url


async def test_data_table_excel_string_patch_delete_and_export(
    office_client,
    auth_headers_system,
    unique_id: str,
) -> None:
    require_s3_configured()
    original_name = f"typed-{unique_id}.sqlite"
    create_response = await office_client.post(
        "/documents/api/v1/data-tables",
        headers=auth_headers_system,
        json={
            "original_name": original_name,
            "scope": "office_document",
            "tables": [
                {
                    "name": "typed",
                    "columns": [
                        {"name": "title", "column_type": "text"},
                        {"name": "score", "column_type": "integer"},
                        {"name": "ratio", "column_type": "real"},
                        {"name": "flag", "column_type": "boolean"},
                        {"name": "seen_at", "column_type": "datetime"},
                        {"name": "meta", "column_type": "json"},
                        {"name": "doc", "column_type": "file_ref"},
                    ],
                }
            ],
        },
    )
    assert create_response.status_code == 200, create_response.text
    file_id = create_response.json()["file_id"]
    insert_response = await office_client.post(
        f"/documents/api/v1/data-tables/{file_id}/tables/typed/rows",
        headers=auth_headers_system,
        json={
            "rows": [
                {
                    "title": "Ada",
                    "score": 10,
                    "ratio": 1.5,
                    "flag": True,
                    "seen_at": "2026-08-14T12:00:00+00:00",
                    "meta": {"a": 1},
                    "doc": "file_abc",
                }
            ]
        },
    )
    assert insert_response.status_code == 200, insert_response.text
    row_id = insert_response.json()["row_ids"][0]

    string_int = await office_client.patch(
        f"/documents/api/v1/data-tables/{file_id}/tables/typed/rows/{row_id}",
        headers=auth_headers_system,
        json={"values": {"score": "42"}},
    )
    assert string_int.status_code == 200, string_int.text

    empty_int = await office_client.patch(
        f"/documents/api/v1/data-tables/{file_id}/tables/typed/rows/{row_id}",
        headers=auth_headers_system,
        json={"values": {"score": ""}},
    )
    assert empty_int.status_code == 200, empty_int.text

    invalid_int = await office_client.patch(
        f"/documents/api/v1/data-tables/{file_id}/tables/typed/rows/{row_id}",
        headers=auth_headers_system,
        json={"values": {"score": "nope"}},
    )
    assert invalid_int.status_code == 400, invalid_int.text

    flag_patch = await office_client.patch(
        f"/documents/api/v1/data-tables/{file_id}/tables/typed/rows/{row_id}",
        headers=auth_headers_system,
        json={"values": {"flag": "false", "ratio": "2.25", "meta": '{"b": 2}'}},
    )
    assert flag_patch.status_code == 200, flag_patch.text

    page_response = await office_client.get(
        f"/documents/api/v1/data-tables/{file_id}/tables/typed/rows",
        headers=auth_headers_system,
        params={"limit": 50},
    )
    assert page_response.status_code == 200, page_response.text
    values = page_response.json()["items"][0]["values"]
    assert values["title"] == "Ada"
    assert values["score"] is None
    assert values["ratio"] == 2.25
    assert values["flag"] is False
    assert values["meta"] == {"b": 2}

    csv_response = await office_client.get(
        f"/documents/api/v1/data-tables/{file_id}/tables/typed/export",
        headers=auth_headers_system,
        params={"format": "csv"},
    )
    assert csv_response.status_code == 200, csv_response.text
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=\"typed.csv\"" in csv_response.headers["content-disposition"]
    csv_columns, csv_rows = parse_tabular_bytes(csv_response.content, source_format="csv")
    assert [column.name for column in csv_columns] == [
        "title",
        "score",
        "ratio",
        "flag",
        "seen_at",
        "meta",
        "doc",
    ]
    assert csv_rows[0]["title"] == "Ada"
    assert csv_rows[0]["flag"] == "false"

    xlsx_response = await office_client.get(
        f"/documents/api/v1/data-tables/{file_id}/tables/typed/export",
        headers=auth_headers_system,
        params={"format": "xlsx"},
    )
    assert xlsx_response.status_code == 200, xlsx_response.text
    assert "spreadsheetml.sheet" in xlsx_response.headers["content-type"]
    assert "attachment; filename=\"typed.xlsx\"" in xlsx_response.headers["content-disposition"]
    xlsx_columns, xlsx_rows = parse_tabular_bytes(
        xlsx_response.content, source_format="xlsx"
    )
    assert [column.name for column in xlsx_columns] == [
        "title",
        "score",
        "ratio",
        "flag",
        "seen_at",
        "meta",
        "doc",
    ]
    assert xlsx_rows[0]["title"] == "Ada"

    delete_response = await office_client.post(
        f"/documents/api/v1/data-tables/{file_id}/tables/typed/rows/delete",
        headers=auth_headers_system,
        json={"row_ids": [row_id]},
    )
    assert delete_response.status_code == 200, delete_response.text
    assert delete_response.json()["deleted"] == 1
    empty_page = await office_client.get(
        f"/documents/api/v1/data-tables/{file_id}/tables/typed/rows",
        headers=auth_headers_system,
        params={"limit": 50},
    )
    assert empty_page.status_code == 200, empty_page.text
    assert empty_page.json()["items"] == []


async def test_data_table_all_column_types_excel_strings_persist(
    office_client,
    auth_headers_system,
    unique_id: str,
) -> None:
    require_s3_configured()
    file_id = await _create_data_table(
        office_client,
        auth_headers_system,
        original_name=f"matrix-{unique_id}.sqlite",
        tables=[{"name": "typed", "columns": _ALL_TYPED_COLUMNS}],
    )
    insert_response = await office_client.post(
        f"/documents/api/v1/data-tables/{file_id}/tables/typed/rows",
        headers=auth_headers_system,
        json={
            "rows": [
                {
                    "title": "Ada",
                    "score": "10",
                    "ratio": "1.5",
                    "flag": "yes",
                    "seen_at": "2026-08-14T12:00:00Z",
                    "meta": "[1, 2]",
                    "doc": "  file_seed  ",
                }
            ]
        },
    )
    assert insert_response.status_code == 200, insert_response.text
    row_id = insert_response.json()["row_ids"][0]
    seeded = (await _page_items(office_client, auth_headers_system, file_id, "typed"))["items"][0][
        "values"
    ]
    assert seeded["title"] == "Ada"
    assert seeded["score"] == 10
    assert seeded["ratio"] == 1.5
    assert seeded["flag"] is True
    assert isinstance(seeded["seen_at"], str)
    assert seeded["seen_at"].startswith("2026-08-14T12:00:00")
    assert seeded["meta"] == [1, 2]
    assert seeded["doc"] == "file_seed"

    boolean_aliases = (("true", True), ("1", True), ("yes", True), ("false", False), ("0", False), ("no", False))
    for token, expected in boolean_aliases:
        patched = await _patch_row(
            office_client,
            auth_headers_system,
            file_id,
            "typed",
            row_id,
            {"flag": token},
        )
        assert patched.status_code == 200, patched.text
        values = (await _page_items(office_client, auth_headers_system, file_id, "typed"))["items"][0][
            "values"
        ]
        assert values["flag"] is expected, token

    mixed = await _patch_row(
        office_client,
        auth_headers_system,
        file_id,
        "typed",
        row_id,
        {
            "title": "  Ada  ",
            "score": "-7",
            "ratio": "1e2",
            "seen_at": "2026-08-14T15:30:00+00:00",
            "meta": '{"b": 2}',
            "doc": "file_abc",
        },
    )
    assert mixed.status_code == 200, mixed.text
    values = (await _page_items(office_client, auth_headers_system, file_id, "typed"))["items"][0][
        "values"
    ]
    # HTTP payload идёт через StrictBaseModel(str_strip_whitespace=True).
    assert values["title"] == "Ada"
    assert values["score"] == -7
    assert values["ratio"] == 100.0
    assert values["flag"] is False
    assert values["seen_at"] == "2026-08-14T15:30:00+00:00"
    assert values["meta"] == {"b": 2}
    assert values["doc"] == "file_abc"

    cleared = await _patch_row(
        office_client,
        auth_headers_system,
        file_id,
        "typed",
        row_id,
        {
            "title": "",
            "score": "  ",
            "ratio": "",
            "flag": "",
            "seen_at": "   ",
            "meta": "",
            "doc": "",
        },
    )
    assert cleared.status_code == 200, cleared.text
    emptied = (await _page_items(office_client, auth_headers_system, file_id, "typed"))["items"][0][
        "values"
    ]
    assert emptied == {
        "title": None,
        "score": None,
        "ratio": None,
        "flag": None,
        "seen_at": None,
        "meta": None,
        "doc": None,
    }


async def test_data_table_invalid_excel_strings_rejected_per_type(
    office_client,
    auth_headers_system,
    unique_id: str,
) -> None:
    require_s3_configured()
    file_id = await _create_data_table(
        office_client,
        auth_headers_system,
        original_name=f"invalid-{unique_id}.sqlite",
        tables=[{"name": "typed", "columns": _ALL_TYPED_COLUMNS}],
    )
    insert_response = await office_client.post(
        f"/documents/api/v1/data-tables/{file_id}/tables/typed/rows",
        headers=auth_headers_system,
        json={"rows": [{"title": "keep", "score": 1}]},
    )
    assert insert_response.status_code == 200, insert_response.text
    row_id = insert_response.json()["row_ids"][0]
    invalid_values: list[dict[str, Any]] = [
        {"title": 12},
        {"score": "nope"},
        {"score": "42.0"},
        {"score": True},
        {"ratio": "abc"},
        {"ratio": "true"},
        {"flag": "maybe"},
        {"flag": 1},
        {"seen_at": "not-a-date"},
        {"seen_at": 12},
        {"meta": "{"},
        {"doc": 12},
    ]
    for values in invalid_values:
        patched = await _patch_row(
            office_client,
            auth_headers_system,
            file_id,
            "typed",
            row_id,
            values,
        )
        assert patched.status_code == 400, (values, patched.text)
    kept = (await _page_items(office_client, auth_headers_system, file_id, "typed"))["items"][0][
        "values"
    ]
    assert kept["title"] == "keep"
    assert kept["score"] == 1


async def test_data_table_not_null_rejects_empty_string(
    office_client,
    auth_headers_system,
    unique_id: str,
) -> None:
    require_s3_configured()
    file_id = await _create_data_table(
        office_client,
        auth_headers_system,
        original_name=f"required-{unique_id}.sqlite",
        tables=[
            {
                "name": "required",
                "columns": [
                    {"name": "code", "column_type": "integer", "not_null": True},
                    {"name": "label", "column_type": "text"},
                ],
            }
        ],
    )
    missing = await office_client.post(
        f"/documents/api/v1/data-tables/{file_id}/tables/required/rows",
        headers=auth_headers_system,
        json={"rows": [{"label": "x"}]},
    )
    assert missing.status_code == 400, missing.text
    insert_response = await office_client.post(
        f"/documents/api/v1/data-tables/{file_id}/tables/required/rows",
        headers=auth_headers_system,
        json={"rows": [{"code": 1, "label": "x"}]},
    )
    assert insert_response.status_code == 200, insert_response.text
    row_id = insert_response.json()["row_ids"][0]
    empty_patch = await _patch_row(
        office_client,
        auth_headers_system,
        file_id,
        "required",
        row_id,
        {"code": ""},
    )
    assert empty_patch.status_code == 400, empty_patch.text
    kept = (await _page_items(office_client, auth_headers_system, file_id, "required"))["items"][0][
        "values"
    ]
    assert kept["code"] == 1
    assert kept["label"] == "x"


async def test_data_table_schema_import_paging_and_export_isolation(
    office_client,
    auth_headers_system,
    unique_id: str,
) -> None:
    require_s3_configured()
    file_id = await _create_data_table(
        office_client,
        auth_headers_system,
        original_name=f"ops-{unique_id}.sqlite",
        tables=[
            {
                "name": "alpha",
                "columns": [{"name": "title", "column_type": "text"}],
            }
        ],
    )
    added_table = await office_client.post(
        f"/documents/api/v1/data-tables/{file_id}/tables",
        headers=auth_headers_system,
        json={
            "name": "beta",
            "columns": [{"name": "title", "column_type": "text"}],
        },
    )
    assert added_table.status_code == 200, added_table.text
    schema_tables = {table["name"] for table in added_table.json()["tables"]}
    assert schema_tables == {"alpha", "beta"}

    added_column = await office_client.post(
        f"/documents/api/v1/data-tables/{file_id}/tables/alpha/columns",
        headers=auth_headers_system,
        json={"name": "note", "column_type": "text"},
    )
    assert added_column.status_code == 200, added_column.text
    alpha_columns = next(
        table["columns"] for table in added_column.json()["tables"] if table["name"] == "alpha"
    )
    assert [column["name"] for column in alpha_columns] == ["title", "note"]

    insert_alpha = await office_client.post(
        f"/documents/api/v1/data-tables/{file_id}/tables/alpha/rows",
        headers=auth_headers_system,
        json={
            "rows": [
                {"title": "alpha_one", "note": "n1"},
                {"title": "alpha_two", "note": "n2"},
                {"title": "alpha_three", "note": "n3"},
            ]
        },
    )
    assert insert_alpha.status_code == 200, insert_alpha.text
    insert_beta = await office_client.post(
        f"/documents/api/v1/data-tables/{file_id}/tables/beta/rows",
        headers=auth_headers_system,
        json={"rows": [{"title": "beta_secret"}]},
    )
    assert insert_beta.status_code == 200, insert_beta.text

    first_page = await _page_items(
        office_client, auth_headers_system, file_id, "alpha", limit=2
    )
    assert first_page["has_more"] is True
    assert len(first_page["items"]) == 2
    assert isinstance(first_page["next_cursor"], str)
    assert first_page["next_cursor"] != ""
    second_page = await _page_items(
        office_client,
        auth_headers_system,
        file_id,
        "alpha",
        limit=2,
        cursor=first_page["next_cursor"],
    )
    assert second_page["has_more"] is False
    titles = {
        item["values"]["title"]
        for item in [*first_page["items"], *second_page["items"]]
    }
    assert titles == {"alpha_one", "alpha_two", "alpha_three"}

    csv_response = await office_client.get(
        f"/documents/api/v1/data-tables/{file_id}/tables/alpha/export",
        headers=auth_headers_system,
        params={"format": "csv"},
    )
    assert csv_response.status_code == 200, csv_response.text
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert 'filename="alpha.csv"' in csv_response.headers["content-disposition"]
    assert csv_response.content.startswith(b"\xef\xbb\xbf")
    _assert_user_export(
        csv_response.content, source_format="csv", columns=["title", "note"]
    )
    csv_text = csv_response.content.decode("utf-8-sig")
    assert "beta_secret" not in csv_text
    assert "row_id" not in csv_text.splitlines()[0]

    xlsx_response = await office_client.get(
        f"/documents/api/v1/data-tables/{file_id}/tables/alpha/export",
        headers=auth_headers_system,
        params={"format": "xlsx"},
    )
    assert xlsx_response.status_code == 200, xlsx_response.text
    assert "spreadsheetml.sheet" in xlsx_response.headers["content-type"]
    assert 'filename="alpha.xlsx"' in xlsx_response.headers["content-disposition"]
    assert xlsx_response.content.startswith(b"PK")
    _assert_user_export(
        xlsx_response.content, source_format="xlsx", columns=["title", "note"]
    )
    _exported_columns, xlsx_rows = parse_tabular_bytes(
        xlsx_response.content, source_format="xlsx"
    )
    assert [column.name for column in _exported_columns] == ["title", "note"]
    assert {row["title"] for row in xlsx_rows} == {
        "alpha_one",
        "alpha_two",
        "alpha_three",
    }
    assert all(row["title"] != "beta_secret" for row in xlsx_rows)

    sqlite_rejected = await office_client.get(
        f"/documents/api/v1/data-tables/{file_id}/tables/alpha/export",
        headers=auth_headers_system,
        params={"format": "sqlite"},
    )
    assert sqlite_rejected.status_code == 422, sqlite_rejected.text

    csv_bytes = "city,pop\nParis,10\nLyon,8\n".encode("utf-8-sig")
    import_csv = await office_client.post(
        f"/documents/api/v1/data-tables/{file_id}/import",
        headers=auth_headers_system,
        params={"table_name": "imported", "source_format": "csv"},
        files={"upload": ("cities.csv", csv_bytes, "text/csv")},
    )
    assert import_csv.status_code == 200, import_csv.text
    imported_names = {table["name"] for table in import_csv.json()["tables"]}
    assert "imported" in imported_names
    imported_page = await _page_items(
        office_client, auth_headers_system, file_id, "imported"
    )
    assert {
        (item["values"]["city"], item["values"]["pop"])
        for item in imported_page["items"]
    } == {("Paris", "10"), ("Lyon", "8")}

    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    _ = sheet.append(["region", "code"])
    _ = sheet.append(["west", "w1"])
    xlsx_buffer = BytesIO()
    workbook.save(xlsx_buffer)
    import_xlsx = await office_client.post(
        f"/documents/api/v1/data-tables/{file_id}/import",
        headers=auth_headers_system,
        params={"table_name": "fromxlsx", "source_format": "xlsx"},
        files={
            "upload": (
                "regions.xlsx",
                xlsx_buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert import_xlsx.status_code == 200, import_xlsx.text
    xlsx_page = await _page_items(
        office_client, auth_headers_system, file_id, "fromxlsx"
    )
    assert xlsx_page["items"][0]["values"]["region"] == "west"
    assert xlsx_page["items"][0]["values"]["code"] == "w1"
