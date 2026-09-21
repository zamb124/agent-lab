"""Prod-like: GET metadata REST и `op_*` — один handler."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from httpx import AsyncClient

from apps.flows.realtime.operations import (
    op_flows_exception_absorb_allow_names,
    op_flows_execution_limits,
    op_flows_node_types,
    op_flows_resource_types,
)
from apps.flows.src.container import FlowContainer
from apps.flows.src.models.exception_absorb_allow import list_exception_absorb_allow_values
from apps.flows.src.models.execution_limits import get_graph_max_iterations
from apps.flows.src.models.flow_api import (
    FLOW_NODE_TYPE_CARDS,
    FLOW_RESOURCE_TYPE_CARDS,
    FlowExecutionLimits,
    FlowNodeTypeCard,
    FlowResourceTypeCard,
)
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User
from core.pagination import ListResponse
from core.websocket import EmptyPayload
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60)]


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


async def test_node_types_rest_and_op_share_payload(
    client: AsyncClient,
    container: FlowContainer,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    http_resp = await client.get(
        "/flows/api/v1/metadata/node-types",
        headers=auth_headers_system,
    )
    assert http_resp.status_code == 200, http_resp.text
    http_body = ListResponse[FlowNodeTypeCard].model_validate(http_resp.json())
    static_types = {card.type for card in FLOW_NODE_TYPE_CARDS}
    listed_types = {card.type for card in http_body.items}
    assert static_types <= listed_types
    with _system_scope(system_user_id) as user:
        listed = await op_flows_node_types(
            EmptyPayload(),
            user=user,
            container=container,
        )
    assert listed.model_dump(mode="json") == http_resp.json()


async def test_resource_types_rest_and_op_share_payload(
    client: AsyncClient,
    container: FlowContainer,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    http_resp = await client.get(
        "/flows/api/v1/metadata/resource-types",
        headers=auth_headers_system,
    )
    assert http_resp.status_code == 200, http_resp.text
    http_body = ListResponse[FlowResourceTypeCard].model_validate(http_resp.json())
    assert [card.model_dump(mode="json") for card in http_body.items] == [
        card.model_dump(mode="json") for card in FLOW_RESOURCE_TYPE_CARDS
    ]
    with _system_scope(system_user_id) as user:
        listed = await op_flows_resource_types(
            EmptyPayload(),
            user=user,
            container=container,
        )
    assert listed.model_dump(mode="json") == http_resp.json()


async def test_exception_absorb_allow_names_rest_and_op_share_payload(
    client: AsyncClient,
    container: FlowContainer,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    http_resp = await client.get(
        "/flows/api/v1/metadata/exception-absorb-allow-names",
        headers=auth_headers_system,
    )
    assert http_resp.status_code == 200, http_resp.text
    http_body = ListResponse[str].model_validate(http_resp.json())
    assert http_body.items == list_exception_absorb_allow_values()
    with _system_scope(system_user_id) as user:
        listed = await op_flows_exception_absorb_allow_names(
            EmptyPayload(),
            user=user,
            container=container,
        )
    assert listed.model_dump(mode="json") == http_resp.json()


async def test_execution_limits_rest_and_op_share_payload(
    client: AsyncClient,
    container: FlowContainer,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    http_resp = await client.get(
        "/flows/api/v1/metadata/execution-limits",
        headers=auth_headers_system,
    )
    assert http_resp.status_code == 200, http_resp.text
    http_body = FlowExecutionLimits.model_validate(http_resp.json())
    assert http_body.graph_max_iterations == get_graph_max_iterations()
    with _system_scope(system_user_id) as user:
        listed = await op_flows_execution_limits(
            EmptyPayload(),
            user=user,
            container=container,
        )
    assert listed.model_dump(mode="json") == http_resp.json()
