"""Smoke: sync.* capabilities via capability-gateway + живой Sync."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from apps.capability_gateway.container import get_capability_gateway_container
from apps.capability_gateway.services.sync_capabilities import SYNC_CLIENT_METHOD_NAMES
from core.capabilities import (
    CapabilityCallRequest,
    CapabilityExecutionContext,
    CapabilityExecutionTokenClaims,
    execution_token_exp,
    issue_execution_token,
)
from core.clients.sync_client import SyncClient
from core.context import clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.models.identity_models import Company, User
from tests.sync.api._helpers import seed_namespace_via_repo

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("sync_service")]


@contextmanager
def _namespace_context(*, user: User, company: Company, namespace: str) -> Iterator[None]:
    previous = get_context()
    ctx = build_job_context(
        company=company,
        user=user,
        host="",
        trace_id="sync-capability-test",
        session_id="sync-capability",
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
        flow_id="sync-capability-smoke",
        branch_id="main",
        session_id="sync-capability-smoke:ctx",
        task_id="task-sync-capability",
        context_id="ctx-sync-capability",
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


async def test_sync_capabilities_cover_every_client_method() -> None:
    container = get_capability_gateway_container()
    manifest = await container.capability_registry.manifest()
    names = {item.name for item in manifest.capabilities}
    expected = {f"sync.{method}" for method in SYNC_CLIENT_METHOD_NAMES}
    assert expected <= names
    public_methods = {
        name
        for name in dir(SyncClient)
        if not name.startswith("_") and callable(getattr(SyncClient, name))
    }
    assert SYNC_CLIENT_METHOD_NAMES <= public_methods


async def test_sync_capability_create_channel_send_and_list_messages(
    frontend_container,
    unique_id: str,
) -> None:
    company = await frontend_container.company_repository.get("system")
    assert company is not None
    user = await frontend_container.user_repository.get("system")
    assert user is not None
    namespace = f"sync-cap-{unique_id}"
    await seed_namespace_via_repo("system", namespace)

    container = get_capability_gateway_container()
    registry = container.capability_registry
    context = _execution_context(namespace=namespace)
    text = f"hello from capability {unique_id}"

    with _namespace_context(user=user, company=company, namespace=namespace):
        created_response = await registry.call(
            CapabilityCallRequest(
                context=context,
                name="sync.create_channel",
                kwargs={
                    "type": "topic",
                    "name": f"cap_ch_{unique_id}",
                    "namespace": namespace,
                },
            )
        )
    assert created_response.status == "ok", created_response
    created = created_response.result
    assert isinstance(created, dict)
    channel_id = created.get("channel_id")
    assert isinstance(channel_id, str) and channel_id.strip()

    send_response = await registry.call(
        CapabilityCallRequest(
            context=context,
            name="sync.send_message",
            kwargs={"channel_id": channel_id, "text": text},
        )
    )
    assert send_response.status == "ok", send_response

    listed_response = await registry.call(
        CapabilityCallRequest(
            context=context,
            name="sync.list_messages",
            kwargs={"channel_id": channel_id},
        )
    )
    assert listed_response.status == "ok", listed_response
    listed = listed_response.result
    assert isinstance(listed, dict)
    items = listed.get("items")
    assert isinstance(items, list)
    previews = [
        str(item.get("text_preview") or "")
        for item in items
        if isinstance(item, dict)
    ]
    assert any(text in preview for preview in previews)


async def test_python_code_node_sync_create_send_and_list(
    sync_service,
    flows_client_http,
    auth_headers_system,
    unique_id: str,
) -> None:
    _ = sync_service
    namespace = f"sync-code-{unique_id}"
    await seed_namespace_via_repo("system", namespace)
    channel_name = f"code_ch_{unique_id}"
    text = f"hello from code node {unique_id}"
    code = (
        "async def run(args, state):\n"
        "    created = await sync.create_channel(\n"
        '        type="topic",\n'
        f"        name={channel_name!r},\n"
        f"        namespace={namespace!r},\n"
        "    )\n"
        '    channel_id = created["channel_id"]\n'
        "    await sync.send_message(\n"
        "        channel_id=channel_id,\n"
        f"        text={text!r},\n"
        "    )\n"
        "    listed = await sync.list_messages(channel_id=channel_id)\n"
        "    previews = [item.get('text_preview') or '' for item in listed['items']]\n"
        '    return {"channel_id": channel_id, "previews": previews}\n'
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
    assert body["output_state"]["channel_id"]
    previews = body["output_state"]["previews"]
    assert isinstance(previews, list)
    assert any(text in str(preview) for preview in previews)
