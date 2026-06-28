"""Helpers for tests: secrets variables API payloads and service upsert."""

from __future__ import annotations

from typing import Any

from apps.flows.src.container import FlowContainer
from core.variables.models import VariableValueKind, VariableValuePayload, VariableValueSpec

SECRETS_API_PREFIX = "/secrets/api/v1"


def static_variable_write_payload(
    variable_key: str,
    value: str,
    *,
    secret: bool = False,
    shared_for_execution: bool = False,
    public: bool = False,
    description: str = "",
) -> dict[str, Any]:
    return {
        "variable_key": variable_key,
        "payload": {
            "base": {
                "value_kind": VariableValueKind.STATIC.value,
                "value": value,
            },
            "scopes": [],
        },
        "secret": secret,
        "shared_for_execution": shared_for_execution,
        "public": public,
        "description": description,
    }


async def upsert_static_variable_via_service(
    container: FlowContainer,
    variable_key: str,
    value: str,
    *,
    secret: bool = False,
    shared_for_execution: bool = False,
    public: bool = False,
) -> None:
    from core.secrets.models import VariableWriteRequest

    request = VariableWriteRequest(
        variable_key=variable_key,
        payload=VariableValuePayload(
            base=VariableValueSpec(value_kind=VariableValueKind.STATIC, value=value)
        ),
        secret=secret,
        shared_for_execution=shared_for_execution,
        public=public,
    )
    _ = await container.variables_service.upsert(request)


async def delete_variable_via_service(container: FlowContainer, variable_key: str) -> None:
    _ = await container.variables_service.delete_var(variable_key)


async def upsert_static_variable_via_secrets_http(
    secrets_client: Any,
    variable_key: str,
    value: str,
    *,
    secret: bool = False,
    shared_for_execution: bool = False,
    public: bool = False,
) -> dict[str, Any]:
    response = await secrets_client.post(
        f"{SECRETS_API_PREFIX}/variables",
        json=static_variable_write_payload(
            variable_key,
            value,
            secret=secret,
            shared_for_execution=shared_for_execution,
            public=public,
        ),
    )
    if response.status_code != 200:
        raise AssertionError(
            f"secrets variable upsert failed: {response.status_code} {response.text}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise AssertionError("secrets variable upsert returned non-object JSON")
    return payload
