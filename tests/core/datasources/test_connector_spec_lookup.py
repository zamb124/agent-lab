"""Чтение DatasourceConnectorSpec по естественному ключу компании."""

from __future__ import annotations

import pytest

from core.datasources.models import (
    DatasourceConnectorSpec,
    DatasourceExecutorKind,
    DatasourceOperation,
)


@pytest.mark.asyncio
async def test_by_connector_id_returns_own_row_and_hides_other_company(unique_id: str) -> None:
    company_id = f"dsco_{unique_id}"
    other_company_id = f"dsco_other_{unique_id}"
    connector_id = f"conn_{unique_id}"
    owner_user_id = f"user_{unique_id}"
    created = await DatasourceConnectorSpec.upsert_by_connector_id(
        company_id,
        DatasourceConnectorSpec(
            connector_id=connector_id,
            name=f"Lookup {unique_id}",
            description="company connector",
            executor=DatasourceExecutorKind.MCP,
            credential_schema={"type": "object"},
            operations=[DatasourceOperation.QUERY],
            mcp_server_id=f"mcp_{unique_id}",
            mcp_query_tool="query",
            company_id=company_id,
            owner_user_id=owner_user_id,
        ),
        owner_user_id=owner_user_id,
    )

    found = await DatasourceConnectorSpec.by_connector_id(company_id, connector_id)
    assert found is not None
    assert found.connector_id == connector_id
    assert found.company_id == company_id
    assert await DatasourceConnectorSpec.by_connector_id(other_company_id, connector_id) is None
    assert await DatasourceConnectorSpec.by_connector_id(company_id, f"missing_{unique_id}") is None
    with pytest.raises(ValueError, match="connector_id cannot be empty"):
        _ = await DatasourceConnectorSpec.by_connector_id(company_id, "")
    with pytest.raises(ValueError, match="company_id cannot be empty"):
        _ = await DatasourceConnectorSpec.by_connector_id("", connector_id)

    updated = await DatasourceConnectorSpec.upsert_by_connector_id(
        company_id,
        found.model_copy(update={"name": "Renamed", "owner_user_id": f"other_{unique_id}"}),
        owner_user_id=f"other_{unique_id}",
    )
    assert updated.datasource_connector_id == created.datasource_connector_id
    assert updated.created_at == created.created_at
    assert updated.owner_user_id == owner_user_id
    assert updated.name == "Renamed"
    with pytest.raises(ValueError, match="owner_user_id cannot be empty"):
        _ = await DatasourceConnectorSpec.upsert_by_connector_id(
            company_id,
            found,
            owner_user_id="",
        )
