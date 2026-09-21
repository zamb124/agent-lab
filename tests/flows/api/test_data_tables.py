"""Flows HTTP: create DataTable flow_asset, Office snapshot/mutate/export roundtrip."""

from __future__ import annotations

import pytest

from core.data_tables.import_tabular import parse_tabular_bytes
from core.data_tables.models import DATA_TABLE_CONTENT_TYPE
from core.utils.slug import slugify
from tests.fixtures.s3 import require_s3_configured
from tests.office.test_data_tables_api import _export_bytes

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(120)]

_SQLITE_MAGIC = b"SQLite format 3"


async def test_flow_asset_data_table_create_office_roundtrip_and_export(
    flows_client,
    office_client,
    auth_headers_system,
    unique_id: str,
) -> None:
    require_s3_configured()
    flow_id = f"dt_flow_{unique_id}"
    created_flow = await flows_client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers_system,
        json={
            "flow_id": flow_id,
            "name": f"DataTable {unique_id}",
            "entry": "main",
            "nodes": {
                "main": {"type": "llm_node", "prompt": "Test data table flow.", "tools": []}
            },
            "edges": [{"from_node": "main", "to_node": None}],
        },
    )
    assert created_flow.status_code == 200, created_flow.text

    original_name = f"flow-table-{unique_id}.sqlite"
    create_response = await flows_client.post(
        "/flows/api/v1/data-tables",
        headers=auth_headers_system,
        json={
            "original_name": original_name,
            "scope": "flow_asset",
            "flow_id": flow_id,
            "tables": [
                {
                    "name": "leads",
                    "columns": [
                        {"name": "title", "column_type": "text"},
                        {"name": "score", "column_type": "integer"},
                        {"name": "flag", "column_type": "boolean"},
                        {"name": "meta", "column_type": "json"},
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

    catalogs_response = await office_client.get(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
    )
    assert catalogs_response.status_code == 200, catalogs_response.text
    catalog_items = catalogs_response.json()["items"]
    flows_catalog = next(
        (
            item
            for item in catalog_items
            if item["title"] == "Flows" and not item.get("parent_catalog_id")
        ),
        None,
    )
    assert flows_catalog is not None
    flow_catalog = next(
        (
            item
            for item in catalog_items
            if item["title"] == slugify(flow_id)
            and item.get("parent_catalog_id") == flows_catalog["catalog_id"]
        ),
        None,
    )
    assert flow_catalog is not None
    documents_response = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": flow_catalog["catalog_id"]},
        headers=auth_headers_system,
    )
    assert documents_response.status_code == 200, documents_response.text
    assert any(item["file_id"] == file_id for item in documents_response.json()["items"])

    snapshot = await office_client.get(
        f"/documents/api/v1/data-tables/{file_id}",
        headers=auth_headers_system,
    )
    assert snapshot.status_code == 200, snapshot.text
    tables = snapshot.json()["schema_snapshot"]["tables"]
    assert tables[0]["name"] == "leads"
    assert [column["column_type"] for column in tables[0]["columns"]] == [
        "text",
        "integer",
        "boolean",
        "json",
    ]

    insert_response = await office_client.post(
        f"/documents/api/v1/data-tables/{file_id}/tables/leads/rows",
        headers=auth_headers_system,
        json={"rows": [{"title": "Ada", "score": "42", "flag": "yes", "meta": '{"a": 1}'}]},
    )
    assert insert_response.status_code == 200, insert_response.text
    row_id = insert_response.json()["row_ids"][0]
    patched = await office_client.patch(
        f"/documents/api/v1/data-tables/{file_id}/tables/leads/rows/{row_id}",
        headers=auth_headers_system,
        json={"values": {"score": "", "flag": "false", "meta": "[1, 2]"}},
    )
    assert patched.status_code == 200, patched.text
    page = await office_client.get(
        f"/documents/api/v1/data-tables/{file_id}/tables/leads/rows",
        headers=auth_headers_system,
        params={"limit": 50},
    )
    assert page.status_code == 200, page.text
    values = page.json()["items"][0]["values"]
    assert values["title"] == "Ada"
    assert values["score"] is None
    assert values["flag"] is False
    assert values["meta"] == [1, 2]

    _csv_response, csv_export = await _export_bytes(
        office_client, auth_headers_system, file_id, "leads", source_format="csv"
    )
    assert csv_export.startswith(b"\xef\xbb\xbf")
    assert not csv_export.startswith(_SQLITE_MAGIC)
    csv_columns, csv_rows = parse_tabular_bytes(csv_export, source_format="csv")
    assert [column.name for column in csv_columns] == ["title", "score", "flag", "meta"]
    assert csv_rows[0]["title"] == "Ada"
    assert csv_rows[0]["flag"] == "false"

    _xlsx_response, xlsx_export = await _export_bytes(
        office_client, auth_headers_system, file_id, "leads", source_format="xlsx"
    )
    assert xlsx_export.startswith(b"PK")
    assert _SQLITE_MAGIC not in xlsx_export[:64]
    xlsx_columns, xlsx_rows = parse_tabular_bytes(xlsx_export, source_format="xlsx")
    assert [column.name for column in xlsx_columns] == ["title", "score", "flag", "meta"]
    assert xlsx_rows[0]["title"] == "Ada"


async def test_flows_data_table_rejects_office_document_scope(
    flows_client,
    auth_headers_system,
    unique_id: str,
) -> None:
    rejected = await flows_client.post(
        "/flows/api/v1/data-tables",
        headers=auth_headers_system,
        json={
            "original_name": f"office-scope-{unique_id}.sqlite",
            "scope": "office_document",
            "tables": [{"name": "leads", "columns": [{"name": "title", "column_type": "text"}]}],
        },
    )
    assert rejected.status_code == 400, rejected.text
    body = rejected.json()
    assert body["error_code"] == "ws_invalid_payload"
    assert "flow_asset" in body["detail"]
