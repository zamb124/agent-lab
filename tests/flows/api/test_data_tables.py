"""Flows HTTP: create DataTable flow_asset, Office snapshot/mutate/export roundtrip."""

from __future__ import annotations

import pytest

from core.data_tables.import_tabular import parse_tabular_bytes
from core.data_tables.models import DATA_TABLE_CONTENT_TYPE
from tests.fixtures.s3 import require_s3_configured

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

    csv_response = await office_client.get(
        f"/documents/api/v1/data-tables/{file_id}/tables/leads/export",
        headers=auth_headers_system,
        params={"format": "csv"},
    )
    assert csv_response.status_code == 200, csv_response.text
    assert csv_response.content.startswith(b"\xef\xbb\xbf")
    assert not csv_response.content.startswith(_SQLITE_MAGIC)
    csv_columns, csv_rows = parse_tabular_bytes(csv_response.content, source_format="csv")
    assert [column.name for column in csv_columns] == ["title", "score", "flag", "meta"]
    assert csv_rows[0]["title"] == "Ada"
    assert csv_rows[0]["flag"] == "false"

    xlsx_response = await office_client.get(
        f"/documents/api/v1/data-tables/{file_id}/tables/leads/export",
        headers=auth_headers_system,
        params={"format": "xlsx"},
    )
    assert xlsx_response.status_code == 200, xlsx_response.text
    assert xlsx_response.content.startswith(b"PK")
    assert _SQLITE_MAGIC not in xlsx_response.content[:64]
    xlsx_columns, xlsx_rows = parse_tabular_bytes(
        xlsx_response.content, source_format="xlsx"
    )
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
    assert "flow_asset" in rejected.json()["detail"]
