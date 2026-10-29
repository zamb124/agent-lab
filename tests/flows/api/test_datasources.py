"""HTTP CRUD + deny-list + FGA + protocol on live Postgres customer DB."""

from __future__ import annotations

from urllib.parse import urlparse

import pytest
from httpx2 import AsyncClient

from core.config import get_settings
from tests.fixtures.datasources import (
    CUSTOMER_DATABASE,
    CUSTOMER_HOST,
    CUSTOMER_PASSWORD,
    CUSTOMER_PORT,
    CUSTOMER_USERNAME,
    CustomerDatasource,
    platform_shared_database_name,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60)]

_API = "/flows/api/v1/datasources"


def _seed_row(customer: CustomerDatasource) -> dict[str, object]:
    return {"id": customer.seed_id, "name": customer.seed_name}


async def test_datasource_crud_password_absent_in_json(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    customer_datasource: CustomerDatasource,
) -> None:
    datasource_id = customer_datasource.datasource_id
    created = await flows_client.get(
        f"{_API}/{datasource_id}",
        headers=auth_headers_system,
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["datasource_id"] == datasource_id
    assert body["connector_id"] == "postgres"
    assert body["database_name"] == CUSTOMER_DATABASE
    assert body["host"] == CUSTOMER_HOST
    assert body["port"] == CUSTOMER_PORT
    assert body["username"] == CUSTOMER_USERNAME
    assert "password" not in body
    assert "password_encrypted" not in body

    patched_name = f"{body['name']} patched"
    patched = await flows_client.patch(
        f"{_API}/{datasource_id}",
        headers=auth_headers_system,
        json={"name": patched_name},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == patched_name
    assert "password" not in patched.json()

    listed = await flows_client.get(_API, headers=auth_headers_system)
    assert listed.status_code == 200, listed.text
    ids = {item["datasource_id"] for item in listed.json()["items"]}
    assert datasource_id in ids
    for item in listed.json()["items"]:
        assert "password" not in item
        assert "password_encrypted" not in item


async def test_datasource_test_introspect_query_execute(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    customer_datasource: CustomerDatasource,
) -> None:
    datasource_id = customer_datasource.datasource_id
    tested = await flows_client.post(
        f"{_API}/{datasource_id}/test",
        headers=auth_headers_system,
        json={},
    )
    assert tested.status_code == 200, tested.text
    test_body = tested.json()
    assert test_body["ok"] is True
    assert test_body["latency_ms"] >= 0
    assert isinstance(test_body["server_version"], str)
    assert test_body["server_version"].strip()

    introspected = await flows_client.post(
        f"{_API}/{datasource_id}/introspect",
        headers=auth_headers_system,
        json={},
    )
    assert introspected.status_code == 200, introspected.text
    tables = introspected.json()["tables"]
    table_names = {table["table_name"] for table in tables}
    assert customer_datasource.qualified_table in table_names
    matched = next(
        table
        for table in tables
        if table["table_name"] == customer_datasource.qualified_table
    )
    column_names = {column["name"] for column in matched["columns"]}
    assert column_names == {"id", "name"}

    queried = await flows_client.post(
        f"{_API}/{datasource_id}/query",
        headers=auth_headers_system,
        json={
            "sql": customer_datasource.query_by_id_sql,
            "params": {"id": customer_datasource.seed_id},
        },
    )
    assert queried.status_code == 200, queried.text
    query_body = queried.json()
    assert query_body["columns"] == ["id", "name"]
    assert query_body["rows"] == [_seed_row(customer_datasource)]
    assert query_body["row_count"] == 1
    assert query_body["truncated"] is False

    inserted_id = customer_datasource.seed_id + 1
    inserted_name = f"beta-{customer_datasource.schema_name}"
    executed = await flows_client.post(
        f"{_API}/{datasource_id}/execute",
        headers=auth_headers_system,
        json={
            "sql": customer_datasource.insert_sql,
            "params": {"id": inserted_id, "name": inserted_name},
        },
    )
    assert executed.status_code == 200, executed.text
    assert executed.json()["rowcount"] == 1

    after_insert = await flows_client.post(
        f"{_API}/{datasource_id}/query",
        headers=auth_headers_system,
        json={
            "sql": customer_datasource.query_by_id_sql,
            "params": {"id": inserted_id},
        },
    )
    assert after_insert.status_code == 200, after_insert.text
    assert after_insert.json()["rows"] == [{"id": inserted_id, "name": inserted_name}]


async def test_datasource_create_platform_shared_denied(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
) -> None:
    shared_url = get_settings().database.shared_url
    parsed = urlparse(shared_url)
    if parsed.hostname is None:
        raise AssertionError("shared_url must have hostname")
    port = parsed.port if parsed.port is not None else 5432
    denied = await flows_client.post(
        _API,
        headers=auth_headers_system,
        json={
            "connector_id": "postgres",
            "name": "platform shared",
            "host": parsed.hostname,
            "port": port,
            "database_name": platform_shared_database_name(),
            "username": CUSTOMER_USERNAME,
            "password": "admin",
            "ssl_mode": "disable",
            "allowed_operations": ["select"],
        },
    )
    assert denied.status_code == 400, denied.text
    assert "platform DSN" in denied.text


async def test_datasource_fga_foreign_user_denied_list_is_intersection(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    auth_headers_system_user2: dict[str, str],
    auth_headers_company2: dict[str, str],
    customer_datasource: CustomerDatasource,
) -> None:
    datasource_id = customer_datasource.datasource_id

    foreign_get = await flows_client.get(
        f"{_API}/{datasource_id}",
        headers=auth_headers_company2,
    )
    assert foreign_get.status_code == 403, foreign_get.text

    foreign_list = await flows_client.get(_API, headers=auth_headers_company2)
    assert foreign_list.status_code == 200, foreign_list.text
    foreign_ids = {item["datasource_id"] for item in foreign_list.json()["items"]}
    assert datasource_id not in foreign_ids

    member_list = await flows_client.get(_API, headers=auth_headers_system_user2)
    assert member_list.status_code == 200, member_list.text
    member_ids = {item["datasource_id"] for item in member_list.json()["items"]}
    assert datasource_id in member_ids

    owner_list = await flows_client.get(_API, headers=auth_headers_system)
    assert owner_list.status_code == 200, owner_list.text
    owner_ids = {item["datasource_id"] for item in owner_list.json()["items"]}
    assert datasource_id in owner_ids

    member_query = await flows_client.post(
        f"{_API}/{datasource_id}/query",
        headers=auth_headers_system_user2,
        json={
            "sql": customer_datasource.query_by_id_sql,
            "params": {"id": customer_datasource.seed_id},
        },
    )
    assert member_query.status_code == 200, member_query.text
    assert member_query.json()["rows"] == [_seed_row(customer_datasource)]

    member_execute = await flows_client.post(
        f"{_API}/{datasource_id}/execute",
        headers=auth_headers_system_user2,
        json={
            "sql": customer_datasource.insert_sql,
            "params": {"id": 99, "name": "denied"},
        },
    )
    assert member_execute.status_code == 403, member_execute.text


async def test_datasource_delete(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    created = await flows_client.post(
        _API,
        headers=auth_headers_system,
        json={
            "connector_id": "postgres",
            "name": f"delete-me {unique_id}",
            "host": CUSTOMER_HOST,
            "port": CUSTOMER_PORT,
            "database_name": CUSTOMER_DATABASE,
            "username": CUSTOMER_USERNAME,
            "password": "admin",
            "ssl_mode": "disable",
            "allowed_operations": ["select"],
        },
    )
    assert created.status_code == 200, created.text
    datasource_id = created.json()["datasource_id"]
    deleted = await flows_client.delete(
        f"{_API}/{datasource_id}",
        headers=auth_headers_system,
    )
    assert deleted.status_code in {200, 204}, deleted.text
    missing = await flows_client.get(
        f"{_API}/{datasource_id}",
        headers=auth_headers_system,
    )
    assert missing.status_code == 403, missing.text


async def test_datasource_select_only_rejects_insert(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    customer_datasource: CustomerDatasource,
) -> None:
    datasource_id = customer_datasource.datasource_id
    patched = await flows_client.patch(
        f"{_API}/{datasource_id}",
        headers=auth_headers_system,
        json={"allowed_operations": ["select"]},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["allowed_operations"] == ["select"]

    denied = await flows_client.post(
        f"{_API}/{datasource_id}/execute",
        headers=auth_headers_system,
        json={
            "sql": customer_datasource.insert_sql,
            "params": {"id": customer_datasource.seed_id + 1, "name": "denied"},
        },
    )
    assert denied.status_code == 400, denied.text
    assert "allowed_operations" in denied.text


async def test_datasource_create_k8s_host_denied(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    denied = await flows_client.post(
        _API,
        headers=auth_headers_system,
        json={
            "connector_id": "postgres",
            "name": f"k8s {unique_id}",
            "host": "postgres.platform.svc",
            "port": 5432,
            "database_name": "anything",
            "username": CUSTOMER_USERNAME,
            "password": CUSTOMER_PASSWORD,
            "ssl_mode": "disable",
            "allowed_operations": ["select"],
        },
    )
    assert denied.status_code == 400, denied.text
    assert "platform database" in denied.text


async def test_datasource_foreign_company_protocol_denied(
    flows_client: AsyncClient,
    auth_headers_company2: dict[str, str],
    customer_datasource: CustomerDatasource,
) -> None:
    datasource_id = customer_datasource.datasource_id
    foreign_query = await flows_client.post(
        f"{_API}/{datasource_id}/query",
        headers=auth_headers_company2,
        json={
            "sql": customer_datasource.query_by_id_sql,
            "params": {"id": customer_datasource.seed_id},
        },
    )
    assert foreign_query.status_code == 403, foreign_query.text

    foreign_execute = await flows_client.post(
        f"{_API}/{datasource_id}/execute",
        headers=auth_headers_company2,
        json={
            "sql": customer_datasource.insert_sql,
            "params": {"id": 99, "name": "denied"},
        },
    )
    assert foreign_execute.status_code == 403, foreign_execute.text


async def test_datasource_patch_password_absent_in_json(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    customer_datasource: CustomerDatasource,
) -> None:
    datasource_id = customer_datasource.datasource_id
    patched = await flows_client.patch(
        f"{_API}/{datasource_id}",
        headers=auth_headers_system,
        json={"password": CUSTOMER_PASSWORD},
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert "password" not in body
    assert "password_encrypted" not in body

    tested = await flows_client.post(
        f"{_API}/{datasource_id}/test",
        headers=auth_headers_system,
        json={},
    )
    assert tested.status_code == 200, tested.text
    assert tested.json()["ok"] is True


async def test_datasource_patch_k8s_host_denied(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    customer_datasource: CustomerDatasource,
) -> None:
    denied = await flows_client.patch(
        f"{_API}/{customer_datasource.datasource_id}",
        headers=auth_headers_system,
        json={"host": "postgres.platform.svc"},
    )
    assert denied.status_code == 400, denied.text
    assert "platform database" in denied.text


async def test_datasource_stamp_rejects_platform_executor(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    denied = await flows_client.put(
        f"{_API}/connectors",
        headers=auth_headers_system,
        json={
            "connector_id": f"stamp{unique_id}",
            "name": f"stamp {unique_id}",
            "description": "illegal platform stamp",
            "executor": "platform",
            "credential_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "operations": ["query"],
        },
    )
    assert denied.status_code == 400, denied.text
    assert "executor=platform" in denied.text


async def test_datasource_stamp_rejects_reserved_postgres_id(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
) -> None:
    denied = await flows_client.put(
        f"{_API}/connectors",
        headers=auth_headers_system,
        json={
            "connector_id": "postgres",
            "name": "reserved",
            "description": "cannot occupy postgres",
            "executor": "flow",
            "credential_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "operations": ["query"],
            "flow_id": "does-not-matter",
        },
    )
    assert denied.status_code == 400, denied.text
    assert "reserved" in denied.text


async def test_datasource_query_rejects_second_statement(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    customer_datasource: CustomerDatasource,
) -> None:
    denied = await flows_client.post(
        f"{_API}/{customer_datasource.datasource_id}/query",
        headers=auth_headers_system,
        json={"sql": "SELECT 1; SELECT 2", "params": {}},
    )
    assert denied.status_code == 400, denied.text
    assert "exactly one statement" in denied.text


async def test_datasource_query_rejects_unused_named_param(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    customer_datasource: CustomerDatasource,
) -> None:
    denied = await flows_client.post(
        f"{_API}/{customer_datasource.datasource_id}/query",
        headers=auth_headers_system,
        json={
            "sql": customer_datasource.query_by_id_sql,
            "params": {"id": customer_datasource.seed_id, "extra": 1},
        },
    )
    assert denied.status_code == 400, denied.text
    assert "unused" in denied.text


async def test_datasource_query_max_rows_truncates(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    customer_datasource: CustomerDatasource,
) -> None:
    inserted_id = customer_datasource.seed_id + 40
    executed = await flows_client.post(
        f"{_API}/{customer_datasource.datasource_id}/execute",
        headers=auth_headers_system,
        json={
            "sql": customer_datasource.insert_sql,
            "params": {"id": inserted_id, "name": f"trunc-{customer_datasource.schema_name}"},
        },
    )
    assert executed.status_code == 200, executed.text

    patched = await flows_client.patch(
        f"{_API}/{customer_datasource.datasource_id}",
        headers=auth_headers_system,
        json={"max_rows": 1},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["max_rows"] == 1

    queried = await flows_client.post(
        f"{_API}/{customer_datasource.datasource_id}/query",
        headers=auth_headers_system,
        json={
            "sql": f"SELECT id, name FROM {customer_datasource.qualified_table} ORDER BY id",
            "params": {},
        },
    )
    assert queried.status_code == 200, queried.text
    body = queried.json()
    assert body["truncated"] is True
    assert body["row_count"] == 1
    assert len(body["rows"]) == 1


async def test_datasource_missing_id_is_403(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    datasource_id = f"ds_missing_{unique_id}"
    missing_get = await flows_client.get(
        f"{_API}/{datasource_id}",
        headers=auth_headers_system,
    )
    assert missing_get.status_code == 403, missing_get.text

    missing_query = await flows_client.post(
        f"{_API}/{datasource_id}/query",
        headers=auth_headers_system,
        json={"sql": "SELECT 1", "params": {}},
    )
    assert missing_query.status_code == 403, missing_query.text
