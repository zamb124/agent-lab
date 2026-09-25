"""Prod-like: triggers REST и `op_*` — один handler."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from httpx import AsyncClient

from apps.flows.di import FlowsDi
from apps.flows.realtime.operations import FlowsFlowIdPayload
from apps.flows.realtime.trigger_operations import (
    op_flows_platform_events_catalog,
    op_flows_triggers_create,
    op_flows_triggers_item,
    op_flows_triggers_list,
    op_flows_triggers_remove,
)
from apps.flows.src.models import TriggerType
from apps.flows.src.models.trigger_config import (
    TriggerCreatePayload,
    TriggerCreateRequest,
    TriggerFlowIdPayload,
    TriggerResponse,
)
from core.context import reset_context, set_context
from core.events import PlatformEventCatalogResponse
from core.models.context_models import Context
from core.models.identity_models import User
from core.pagination import ListResponse
from core.websocket import EmptyPayload
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60)]


def _flow_create_body(flow_id: str, name: str) -> dict[str, object]:
    return {
        "flow_id": flow_id,
        "name": name,
        "description": "trigger command",
        "entry": "main",
        "nodes": {"main": {"type": "llm_node", "prompt": "Test", "tools": []}},
        "edges": [{"from_node": "main", "to_node": None}],
    }


@contextmanager
def _system_scope(system_user_id: str) -> Generator[User]:
    user = User(user_id=system_user_id, name="System")
    token = set_context(
        Context(
            user=user,
            active_company=make_test_company(company_id="system", name="System"),
            channel="api",
        )
    )
    try:
        yield user
    finally:
        reset_context(token)


async def test_triggers_list_rest_and_op_share_payload(
    client: AsyncClient,
    di: FlowsDi,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    flow_id = f"cmd_trg_{unique_id}"
    created_flow = await client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers_system,
        json=_flow_create_body(flow_id, "Command triggers"),
    )
    assert created_flow.status_code == 200, created_flow.text
    http_resp = await client.get(
        f"/flows/api/v1/flows/{flow_id}/triggers",
        headers=auth_headers_system,
    )
    assert http_resp.status_code == 200, http_resp.text
    _ = ListResponse[TriggerResponse].model_validate(http_resp.json())
    with _system_scope(system_user_id) as user:
        listed = await op_flows_triggers_list(
            FlowsFlowIdPayload(flow_id=flow_id),
            user=user,
            di=di,
        )
    assert listed.model_dump(mode="json") == http_resp.json()


async def test_triggers_create_get_remove_rest_and_op_share_payload(
    client: AsyncClient,
    di: FlowsDi,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    flow_id = f"cmd_trg_mut_{unique_id}"
    created_flow = await client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers_system,
        json=_flow_create_body(flow_id, "Command trigger mutate"),
    )
    assert created_flow.status_code == 200, created_flow.text
    create_request = TriggerCreateRequest(
        trigger_id="wh_cmd",
        name="Webhook cmd",
        type=TriggerType.WEBHOOK,
        enabled=True,
        config={
            "secret_token": "tok",
            "secret_header": "X-Trigger-Secret",
            "allowed_ips": [],
        },
        output_mapping={"content": "body.text"},
    )
    http_create = await client.post(
        f"/flows/api/v1/flows/{flow_id}/triggers",
        headers=auth_headers_system,
        json=create_request.model_dump(mode="json"),
    )
    assert http_create.status_code == 200, http_create.text
    created = TriggerResponse.model_validate(http_create.json())
    assert created.trigger_id == "wh_cmd"

    http_get = await client.get(
        f"/flows/api/v1/flows/{flow_id}/triggers/wh_cmd",
        headers=auth_headers_system,
    )
    assert http_get.status_code == 200, http_get.text
    with _system_scope(system_user_id) as user:
        op_item = await op_flows_triggers_item(
            TriggerFlowIdPayload(flow_id=flow_id, trigger_id="wh_cmd"),
            user=user,
            di=di,
        )
    assert op_item.model_dump(mode="json") == http_get.json()

    http_delete = await client.delete(
        f"/flows/api/v1/flows/{flow_id}/triggers/wh_cmd",
        headers=auth_headers_system,
    )
    assert http_delete.status_code == 200, http_delete.text
    assert http_delete.json() == {"status": "deleted", "trigger_id": "wh_cmd"}

    op_create_body = TriggerCreatePayload.model_validate(
        {
            **create_request.model_dump(mode="json"),
            "flow_id": flow_id,
            "trigger_id": "wh_cmd_op",
        }
    )
    with _system_scope(system_user_id) as user:
        created_op = await op_flows_triggers_create(
            op_create_body, user=user, di=di
        )
        removed = await op_flows_triggers_remove(
            TriggerFlowIdPayload(flow_id=flow_id, trigger_id="wh_cmd_op"),
            user=user,
            di=di,
        )
    assert created_op.trigger_id == "wh_cmd_op"
    assert removed.model_dump(mode="json") == {"status": "deleted", "trigger_id": "wh_cmd_op"}


async def test_platform_events_catalog_rest_and_op_share_payload(
    client: AsyncClient,
    di: FlowsDi,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    http_resp = await client.get(
        "/flows/api/v1/platform-events/catalog",
        headers=auth_headers_system,
    )
    assert http_resp.status_code == 200, http_resp.text
    _ = PlatformEventCatalogResponse.model_validate(http_resp.json())
    with _system_scope(system_user_id) as user:
        catalog = await op_flows_platform_events_catalog(
            EmptyPayload(),
            user=user,
            di=di,
        )
    assert catalog.model_dump(mode="json") == http_resp.json()
