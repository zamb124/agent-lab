"""pytest fixture: echo/slow code-flow для UI E2E flows flows-chat-page."""

from __future__ import annotations

import pytest_asyncio

from tests.ui.e2e.flows_e2e_helpers import (
    flows_api_create_chat_test_flow,
    flows_api_delete_flow,
    flows_doc_flow_id,
)


@pytest_asyncio.fixture
async def flows_chat_test_agent(
    flows_ui,
    auth_token_system: str,
    unique_id: str,
):
    flow_id = flows_doc_flow_id("chat_e2e", unique_id)
    await flows_api_create_chat_test_flow(flows_ui.origin, auth_token_system, flow_id)
    yield flow_id
    await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)


@pytest_asyncio.fixture
async def flows_chat_slow_agent(
    flows_ui,
    auth_token_system: str,
    unique_id: str,
):
    flow_id = flows_doc_flow_id("chat_slow", unique_id)
    await flows_api_create_chat_test_flow(
        flows_ui.origin,
        auth_token_system,
        flow_id,
        slow=True,
    )
    yield flow_id
    await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)
