"""Version history API for company variables."""

from __future__ import annotations

import pytest

from core.variables.models import VariableValueKind, VariableValuePayload, VariableValueSpec
from core.secrets.models import VariableWriteRequest
from tests.secrets.conftest import API_PREFIX


@pytest.mark.asyncio
async def test_list_variable_versions(secrets_client, unique_id: str) -> None:
    variable_key = f"test_versions_{unique_id}"
    first = VariableWriteRequest(
        variable_key=variable_key,
        payload=VariableValuePayload(
            base=VariableValueSpec(value_kind=VariableValueKind.STATIC, value="v1")
        ),
    )
    second = VariableWriteRequest(
        variable_key=variable_key,
        payload=VariableValuePayload(
            base=VariableValueSpec(value_kind=VariableValueKind.STATIC, value="v2")
        ),
    )
    await secrets_client.post(f"{API_PREFIX}/variables", json=first.model_dump(mode="json"))
    await secrets_client.post(f"{API_PREFIX}/variables", json=second.model_dump(mode="json"))

    versions_resp = await secrets_client.get(f"{API_PREFIX}/variables/{variable_key}/versions")
    assert versions_resp.status_code == 200
    page = versions_resp.json()
    assert page["total"] == 2
    assert len(page["items"]) == 2
    assert page["items"][0]["version"] == 2
    assert page["items"][1]["version"] == 1
