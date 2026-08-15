"""Smoke: crm.* capabilities via capability-gateway + живой CRM."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from apps.capability_gateway.container import get_capability_gateway_container
from apps.capability_gateway.services.crm_capabilities import CRM_CLIENT_METHOD_NAMES
from core.capabilities import (
    CapabilityCallRequest,
    CapabilityExecutionContext,
    CapabilityExecutionTokenClaims,
    execution_token_exp,
    issue_execution_token,
)
from core.clients.crm_client import CrmClient
from core.context import clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.models.identity_models import Company, User

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("crm_service")]


@contextmanager
def _namespace_context(*, user: User, company: Company, namespace: str) -> Iterator[None]:
    previous = get_context()
    ctx = build_job_context(
        company=company,
        user=user,
        host="",
        trace_id="crm-capability-test",
        session_id="crm-capability",
        channel="test",
    )
    set_context(ctx.model_copy(update={"active_namespace": namespace}))
    try:
        yield
    finally:
        if previous is None:
            clear_context()
        else:
            set_context(previous)


def _execution_context(*, namespace: str) -> CapabilityExecutionContext:
    claims = CapabilityExecutionTokenClaims(
        company_id="system",
        user_id="system",
        flow_id="crm-capability-smoke",
        branch_id="main",
        session_id="crm-capability-smoke:ctx",
        task_id="task-crm-capability",
        context_id="ctx-crm-capability",
        channel="test",
        namespace=namespace,
        exp=execution_token_exp(120),
    )
    token = issue_execution_token(claims)
    return CapabilityExecutionContext(
        execution_token=token,
        company_id=claims.company_id,
        user_id=claims.user_id,
        flow_id=claims.flow_id,
        branch_id=claims.branch_id,
        session_id=claims.session_id,
        task_id=claims.task_id,
        context_id=claims.context_id,
        channel=claims.channel,
        namespace=namespace,
    )


async def test_crm_capabilities_cover_every_client_method() -> None:
    container = get_capability_gateway_container()
    manifest = await container.capability_registry.manifest()
    names = {item.name for item in manifest.capabilities}
    expected = {f"crm.{method}" for method in CRM_CLIENT_METHOD_NAMES}
    assert expected <= names
    public_methods = {
        name
        for name in dir(CrmClient)
        if not name.startswith("_") and callable(getattr(CrmClient, name))
    }
    assert CRM_CLIENT_METHOD_NAMES <= public_methods


async def test_crm_capability_create_and_get_entity(
    crm_client,
    frontend_container,
    unique_id: str,
) -> None:
    _ = crm_client
    company = await frontend_container.company_repository.get("system")
    assert company is not None
    user = await frontend_container.user_repository.get("system")
    assert user is not None
    namespace = f"g_{unique_id}"
    name = f"Capability person {unique_id}"
    container = get_capability_gateway_container()
    registry = container.capability_registry
    context = _execution_context(namespace=namespace)

    with _namespace_context(user=user, company=company, namespace=namespace):
        created_response = await registry.call(
            CapabilityCallRequest(
                context=context,
                name="crm.create_entity",
                kwargs={
                    "entity_type": "contact",
                    "name": name,
                    "namespace": namespace,
                },
            )
        )
    assert created_response.status == "ok", created_response
    created = created_response.result
    assert isinstance(created, dict)
    entity = created.get("entity")
    assert isinstance(entity, dict)
    entity_id = entity.get("entity_id")
    assert isinstance(entity_id, str) and entity_id.strip()

    got_response = await registry.call(
        CapabilityCallRequest(
            context=context,
            name="crm.get_entity",
            kwargs={"entity_id": entity_id},
        )
    )
    assert got_response.status == "ok", got_response
    body = got_response.result
    assert isinstance(body, dict)
    got_entity = body.get("entity")
    assert isinstance(got_entity, dict)
    assert got_entity.get("entity_id") == entity_id
    assert got_entity.get("name") == name


async def test_python_code_node_crm_create_and_get_entity(
    crm_client,
    crm_service,
    flows_client_http,
    auth_headers_system,
    unique_id: str,
) -> None:
    _ = crm_client, crm_service
    name = f"Code node person {unique_id}"
    namespace = f"g_{unique_id}"
    code = (
        "async def run(args, state):\n"
        "    created = await crm.create_entity(\n"
        '        entity_type="contact",\n'
        f"        name={name!r},\n"
        f"        namespace={namespace!r},\n"
        "    )\n"
        '    entity_id = created["entity"]["entity_id"]\n'
        "    got = await crm.get_entity(entity_id=entity_id)\n"
        '    return {"entity_id": entity_id, "name": got["entity"]["name"]}\n'
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
            "state": {},
        },
        headers=auth_headers_system,
        timeout=180.0,
    )
    response.raise_for_status()
    body = response.json()
    assert body["success"] is True, body
    assert body["output_state"]["entity_id"]
    assert body["output_state"]["name"] == name
