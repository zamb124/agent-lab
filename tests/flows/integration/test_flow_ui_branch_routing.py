"""Branch routing for Flow UI: the requested branch owns the interface it opens.

Pressing Run on a branch must bootstrap that branch's interface, not the base one.
The branch travels in A2A `params.metadata.branch`, so these tests drive the real
HTTP path instead of calling the session service directly.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from apps.flows.src.container import get_container
from core.a2a import PLATFORM_UI_BOOTSTRAP_ACTION
from core.context import require_context
from apps.flows.src.models.flow_config import BranchConfig
from core.models.flow_interface import (
    FlowInterfaceConfig,
    FlowInterfaceOverride,
    FlowUIDocumentTemplate,
    build_default_chat_document,
    default_flow_interface_config,
)
from tests.flows._a2a_v1 import SEND_MESSAGE, a2a_rpc
from tests.flows._flow_ui_session import (
    a2a_flow_ui_send,
    flow_ui_a2a_headers,
    flow_ui_protojson_message,
)
from tests.flows.a2a_conformance.helpers.flows import create_echo_flow, delete_flow


def _interface_with_greeting(greeting: str) -> FlowInterfaceConfig:
    """A recognisable interface: the greeting identifies which one was opened."""
    base = default_flow_interface_config()
    document = build_default_chat_document(policy=base.policy)
    surface = document.surfaces["main"]
    surface.data_model.content["greeting"] = greeting
    return FlowInterfaceConfig(
        template=FlowUIDocumentTemplate(
            template_id=base.template.template_id,
            version=base.template.version,
            document=document,
        ),
        policy=base.policy,
    )


async def _seed_branch_interface(
    *, flow_id: str, branch_id: str, base_greeting: str, branch_greeting: str
) -> None:
    container = get_container()
    config = await container.flow_repository.get(flow_id)
    assert config is not None
    config.interface = _interface_with_greeting(base_greeting)
    config.branches = {
        branch_id: BranchConfig(
            name="CRM",
            interface_override=FlowInterfaceOverride(
                mode="replace",
                replacement=_interface_with_greeting(branch_greeting),
            ),
        )
    }
    await container.flow_repository.set(config)


async def _document_greeting(session_id: str) -> str:
    state = await get_container().workflow_runtime.get_state(session_id)
    assert state is not None, f"missing Flow UI session {session_id}"
    return str(state.ui_document.surfaces["main"].data_model.content["greeting"])


@pytest.mark.asyncio
async def test_bootstrap_opens_the_requested_branch_interface(
    client: AsyncClient,
    unique_id: str,
) -> None:
    _ = require_context()
    flow_id = f"branch_ui_{unique_id}"
    branch_id = f"crm_{unique_id}"
    base_greeting = f"base-{unique_id}"
    branch_greeting = f"branch-{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        await _seed_branch_interface(
            flow_id=flow_id,
            branch_id=branch_id,
            base_greeting=base_greeting,
            branch_greeting=branch_greeting,
        )

        branch_context = f"ctx-branch-{unique_id}"
        result = await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_BOOTSTRAP_ACTION,
            context_id=branch_context,
            action_id=f"bootstrap-branch-{unique_id}",
            branch_id=branch_id,
        )
        assert result["contextId"] == branch_context
        assert await _document_greeting(f"{flow_id}:{branch_context}") == branch_greeting

        base_context = f"ctx-base-{unique_id}"
        await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_BOOTSTRAP_ACTION,
            context_id=base_context,
            action_id=f"bootstrap-base-{unique_id}",
            branch_id="default",
        )
        assert await _document_greeting(f"{flow_id}:{base_context}") == base_greeting
    finally:
        await delete_flow(client, flow_id)


@pytest.mark.asyncio
async def test_bootstrap_without_branch_metadata_opens_base(
    client: AsyncClient,
    unique_id: str,
) -> None:
    _ = require_context()
    flow_id = f"branch_ui_default_{unique_id}"
    branch_id = f"crm_{unique_id}"
    base_greeting = f"base-{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        await _seed_branch_interface(
            flow_id=flow_id,
            branch_id=branch_id,
            base_greeting=base_greeting,
            branch_greeting=f"branch-{unique_id}",
        )
        context_id = f"ctx-nobranch-{unique_id}"
        await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_BOOTSTRAP_ACTION,
            context_id=context_id,
            action_id=f"bootstrap-nobranch-{unique_id}",
        )
        assert await _document_greeting(f"{flow_id}:{context_id}") == base_greeting
    finally:
        await delete_flow(client, flow_id)


@pytest.mark.asyncio
async def test_second_branch_cannot_take_over_a_live_session(
    client: AsyncClient,
    unique_id: str,
) -> None:
    """A session owns its branch: asking for another one on the same context fails."""
    _ = require_context()
    flow_id = f"branch_ui_conflict_{unique_id}"
    branch_id = f"crm_{unique_id}"
    other_branch_id = f"support_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        await _seed_branch_interface(
            flow_id=flow_id,
            branch_id=branch_id,
            base_greeting=f"base-{unique_id}",
            branch_greeting=f"branch-{unique_id}",
        )
        context_id = f"ctx-conflict-{unique_id}"
        await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_BOOTSTRAP_ACTION,
            context_id=context_id,
            action_id=f"bootstrap-conflict-{unique_id}",
            branch_id=branch_id,
        )

        payload = a2a_rpc(
            SEND_MESSAGE,
            {
                "message": flow_ui_protojson_message(
                    action=PLATFORM_UI_BOOTSTRAP_ACTION,
                    context_id=context_id,
                    action_id=f"bootstrap-takeover-{unique_id}",
                ),
                "metadata": {"branch": other_branch_id},
            },
            rpc_id=f"rpc-takeover-{unique_id}",
        )
        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=flow_ui_a2a_headers(),
            json=payload,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert "error" in body, body
        assert other_branch_id in body["error"]["message"]

        # The live session kept its own branch.
        state = await get_container().workflow_runtime.get_state(f"{flow_id}:{context_id}")
        assert state is not None
        assert state.branch_id == branch_id
    finally:
        await delete_flow(client, flow_id)


@pytest.mark.asyncio
async def test_session_deep_link_without_branch_keeps_running_its_branch(
    client: AsyncClient,
    unique_id: str,
) -> None:
    """Session URLs may carry no branch; `default` must not reset the session."""
    _ = require_context()
    flow_id = f"branch_ui_deeplink_{unique_id}"
    branch_id = f"crm_{unique_id}"
    branch_greeting = f"branch-{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        await _seed_branch_interface(
            flow_id=flow_id,
            branch_id=branch_id,
            base_greeting=f"base-{unique_id}",
            branch_greeting=branch_greeting,
        )
        context_id = f"ctx-deeplink-{unique_id}"
        await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_BOOTSTRAP_ACTION,
            context_id=context_id,
            action_id=f"bootstrap-deeplink-{unique_id}",
            branch_id=branch_id,
        )
        await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_BOOTSTRAP_ACTION,
            context_id=context_id,
            action_id=f"reopen-deeplink-{unique_id}",
            branch_id="default",
        )
        state = await get_container().workflow_runtime.get_state(f"{flow_id}:{context_id}")
        assert state is not None
        assert state.branch_id == branch_id
        assert await _document_greeting(f"{flow_id}:{context_id}") == branch_greeting
    finally:
        await delete_flow(client, flow_id)


@pytest.mark.asyncio
async def test_branch_recorded_on_the_flow_ui_session(
    client: AsyncClient,
    unique_id: str,
) -> None:
    """The durable session must remember which branch it runs, for resume and submit."""
    _ = require_context()
    flow_id = f"branch_ui_state_{unique_id}"
    branch_id = f"crm_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        await _seed_branch_interface(
            flow_id=flow_id,
            branch_id=branch_id,
            base_greeting=f"base-{unique_id}",
            branch_greeting=f"branch-{unique_id}",
        )
        context_id = f"ctx-state-{unique_id}"
        await a2a_flow_ui_send(
            client,
            flow_id=flow_id,
            action=PLATFORM_UI_BOOTSTRAP_ACTION,
            context_id=context_id,
            action_id=f"bootstrap-state-{unique_id}",
            branch_id=branch_id,
        )
        state = await get_container().workflow_runtime.get_state(f"{flow_id}:{context_id}")
        assert state is not None
        assert state.branch_id == branch_id
    finally:
        await delete_flow(client, flow_id)
