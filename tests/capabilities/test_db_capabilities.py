"""Live db.* capabilities through code-node sandbox."""

from __future__ import annotations

import pytest
from httpx2 import AsyncClient

from core.types import require_json_object
from tests.fixtures.datasources import CustomerDatasource

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(180)]


async def test_db_capabilities_in_manifest(capability_gateway_di) -> None:
    manifest = await capability_gateway_di.capability_registry.manifest()
    names = {item.name for item in manifest.capabilities}
    assert "db.schema" in names
    assert "db.query" in names
    assert "db.execute" in names
    schema = next(item for item in manifest.capabilities if item.name == "db.schema")
    assert schema.sdk_namespace == "db"
    assert schema.sdk_method == "schema"


async def test_python_code_node_db_schema_query_execute(
    sandbox_services: dict[str, str],
    flows_client_http: AsyncClient,
    auth_headers_system: dict[str, str],
    customer_datasource: CustomerDatasource,
    unique_id: str,
) -> None:
    _ = sandbox_services
    inserted_id = customer_datasource.seed_id + 20
    inserted_name = f"cap-{unique_id}"
    code = (
        "async def run(args, state):\n"
        "    datasource_id = state['datasource_id']\n"
        "    schema = await db.schema(datasource_id=datasource_id)\n"
        "    queried = await db.query(\n"
        "        datasource_id=datasource_id,\n"
        "        sql=state['query_sql'],\n"
        "        params={'id': state['seed_id']},\n"
        "    )\n"
        "    executed = await db.execute(\n"
        "        datasource_id=datasource_id,\n"
        "        sql=state['insert_sql'],\n"
        "        params={'id': state['insert_id'], 'name': state['insert_name']},\n"
        "    )\n"
        "    return {\n"
        "        'tables': schema['tables'],\n"
        "        'query_rows': queried['rows'],\n"
        "        'rowcount': executed['rowcount'],\n"
        "    }\n"
    )
    response = await flows_client_http.post(
        "/flows/api/v1/code/execute",
        json={
            "node_type": "code",
            "node_config": {
                "type": "code",
                "language": "python",
                "code": code,
            },
            "state": {
                "datasource_id": customer_datasource.datasource_id,
                "query_sql": customer_datasource.query_by_id_sql,
                "insert_sql": customer_datasource.insert_sql,
                "seed_id": customer_datasource.seed_id,
                "insert_id": inserted_id,
                "insert_name": inserted_name,
            },
        },
        headers=auth_headers_system,
        timeout=180.0,
    )
    response.raise_for_status()
    body = response.json()
    assert body["success"] is True, body
    output = body["output_state"]
    tables = output["tables"]
    if not isinstance(tables, list):
        raise AssertionError("db.schema tables must be a list")
    table_names: list[str] = []
    for table in tables:
        table_obj = require_json_object(table, "db.schema.table")
        table_name = table_obj["table_name"]
        if not isinstance(table_name, str):
            raise AssertionError("db.schema.table_name must be str")
        table_names.append(table_name)
    assert customer_datasource.qualified_table in table_names
    assert output["query_rows"] == [
        {"id": customer_datasource.seed_id, "name": customer_datasource.seed_name}
    ]
    assert output["rowcount"] == 1
