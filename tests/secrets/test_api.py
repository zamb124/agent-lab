"""REST API secrets-сервиса: CRUD, версионирование, маскирование, access policy."""

from __future__ import annotations

import pytest

from core.secrets.models import VariableResolveRequest, VariableWriteRequest
from core.variables.models import (
    VariableValueKind,
    VariableValuePayload,
    VariableValueSpec,
)
from tests.secrets.conftest import API_PREFIX


@pytest.mark.asyncio
async def test_upsert_and_get_static_variable(secrets_client, unique_id: str) -> None:
    variable_key = f"test_static_{unique_id}"
    payload = VariableWriteRequest(
        variable_key=variable_key,
        payload=VariableValuePayload(
            base=VariableValueSpec(value_kind=VariableValueKind.STATIC, value="hello")
        ),
        public=True,
        description="test static",
    )
    create_resp = await secrets_client.post(f"{API_PREFIX}/variables", json=payload.model_dump(mode="json"))
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["variable_key"] == variable_key
    assert created["version"] == 1
    assert created["payload"]["base"]["value"] == "hello"

    get_resp = await secrets_client.get(f"{API_PREFIX}/variables/{variable_key}")
    assert get_resp.status_code == 200
    fetched = get_resp.json()
    assert fetched["payload"]["base"]["value"] == "hello"


@pytest.mark.asyncio
async def test_secret_masked_in_api_responses(secrets_client, unique_id: str) -> None:
    variable_key = f"test_secret_{unique_id}"
    secret_value = f"super-secret-{unique_id}"
    payload = VariableWriteRequest(
        variable_key=variable_key,
        secret=True,
        shared_for_execution=True,
        payload=VariableValuePayload(
            base=VariableValueSpec(value_kind=VariableValueKind.STATIC, value=secret_value)
        ),
    )
    create_resp = await secrets_client.post(f"{API_PREFIX}/variables", json=payload.model_dump(mode="json"))
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["secret"] is True
    assert created["payload"]["base"]["value"] is None

    get_resp = await secrets_client.get(f"{API_PREFIX}/variables/{variable_key}")
    assert get_resp.status_code == 200
    assert get_resp.json()["payload"]["base"]["value"] is None

    list_resp = await secrets_client.get(f"{API_PREFIX}/variables")
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    listed = next(item for item in items if item["variable_key"] == variable_key)
    assert listed["payload"]["base"]["value"] is None


@pytest.mark.asyncio
async def test_upsert_increments_version(secrets_client, unique_id: str) -> None:
    variable_key = f"test_version_{unique_id}"
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
    resp1 = await secrets_client.post(f"{API_PREFIX}/variables", json=first.model_dump(mode="json"))
    resp2 = await secrets_client.post(f"{API_PREFIX}/variables", json=second.model_dump(mode="json"))
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["version"] == 1
    assert resp2.json()["version"] == 2


@pytest.mark.asyncio
async def test_shared_secret_resolvable_for_any_user(secrets_client, unique_id: str) -> None:
    variable_key = f"test_shared_{unique_id}"
    payload = VariableWriteRequest(
        variable_key=variable_key,
        secret=True,
        shared_for_execution=True,
        payload=VariableValuePayload(
            base=VariableValueSpec(
                value_kind=VariableValueKind.STATIC,
                value=f"shared-{unique_id}",
            )
        ),
    )
    await secrets_client.post(f"{API_PREFIX}/variables", json=payload.model_dump(mode="json"))

    resolve_resp = await secrets_client.post(
        f"{API_PREFIX}/variables/resolve",
        json=VariableResolveRequest(user_id="other-user").model_dump(mode="json"),
    )
    assert resolve_resp.status_code == 200
    items = resolve_resp.json()["items"]
    resolved = next(item for item in items if item["variable_key"] == variable_key)
    assert resolved["resolvable"] is True
    assert resolved["payload"]["base"]["value"] == f"shared-{unique_id}"


@pytest.mark.asyncio
async def test_private_secret_not_resolvable_for_other_user(
    secrets_client, auth_headers_system, unique_id: str
) -> None:
    from core.utils.tokens import get_token_service

    token = auth_headers_system["Authorization"].removeprefix("Bearer ")
    token_data = get_token_service().validate_token(token)
    assert token_data is not None
    owner_user_id = token_data.user_id

    variable_key = f"test_private_{unique_id}"
    payload = VariableWriteRequest(
        variable_key=variable_key,
        secret=True,
        shared_for_execution=False,
        payload=VariableValuePayload(
            base=VariableValueSpec(
                value_kind=VariableValueKind.STATIC,
                value=f"private-{unique_id}",
            )
        ),
    )
    await secrets_client.post(f"{API_PREFIX}/variables", json=payload.model_dump(mode="json"))

    owner_resp = await secrets_client.post(
        f"{API_PREFIX}/variables/resolve",
        json=VariableResolveRequest(user_id=owner_user_id).model_dump(mode="json"),
    )
    other_resp = await secrets_client.post(
        f"{API_PREFIX}/variables/resolve",
        json=VariableResolveRequest(user_id="foreign-user").model_dump(mode="json"),
    )
    owner_items = owner_resp.json()["items"]
    other_items = other_resp.json()["items"]
    owner_item = next(item for item in owner_items if item["variable_key"] == variable_key)
    other_item = next(item for item in other_items if item["variable_key"] == variable_key)
    assert owner_item["resolvable"] is True
    assert owner_item["payload"]["base"]["value"] == f"private-{unique_id}"
    assert other_item["resolvable"] is False
    assert other_item["payload"] is None


@pytest.mark.asyncio
async def test_delete_variable(secrets_client, unique_id: str) -> None:
    variable_key = f"test_delete_{unique_id}"
    payload = VariableWriteRequest(
        variable_key=variable_key,
        payload=VariableValuePayload(
            base=VariableValueSpec(value_kind=VariableValueKind.STATIC, value="x")
        ),
    )
    await secrets_client.post(f"{API_PREFIX}/variables", json=payload.model_dump(mode="json"))
    delete_resp = await secrets_client.delete(f"{API_PREFIX}/variables/{variable_key}")
    assert delete_resp.status_code == 200
    get_resp = await secrets_client.get(f"{API_PREFIX}/variables/{variable_key}")
    assert get_resp.status_code == 404
