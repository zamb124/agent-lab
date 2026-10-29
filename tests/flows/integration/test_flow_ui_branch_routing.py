"""Ветка владеет интерфейсом сессии: проекция ``state`` идёт по документу запрошенной ветки.

Ветка приходит в A2A ``params.metadata.branch``; тесты идут по реальному HTTP-пути.
"""

from __future__ import annotations

import pytest
from httpx2 import AsyncClient

from apps.flows.src.models import FlowConfig
from apps.flows.src.models.flow_config import BranchConfig
from core.context import require_context
from core.flow_ui.document import FlowUIConversation, FlowUIDocument, FlowUIMarkdownText, FlowUIPage
from tests.flows._flow_ui_session import (
    a2a_send,
    a2a_send_error,
    ensure_flow,
    state_from_task,
    text_message,
)

_NOTES_CODE = (
    "async def run(args, state):\n"
    "    state['base_note'] = 'base'\n"
    "    state['branch_note'] = 'branch'\n"
    "    state['response'] = 'ok'\n"
    "    return state\n"
)


def _interface_showing(field: str) -> FlowUIDocument:
    """Документ с одним текстом ``{field}``: проекция state покажет только это поле."""
    return FlowUIDocument(
        start_page_id="main",
        pages=[
            FlowUIPage(
                page_id="main",
                title="Main",
                blocks=[
                    FlowUIMarkdownText(block_id="note", markdown=f"{{{field}}}"),
                    FlowUIConversation(block_id="conversation"),
                ],
            )
        ],
    )


async def _seed_branch_interface(*, flow_id: str, branch_id: str, di) -> None:
    config = await ensure_flow(
        flow_id=flow_id, interface=_interface_showing("base_note"), code=_NOTES_CODE, di=di
    )
    config.branches = {
        branch_id: BranchConfig(name="CRM", interface=_interface_showing("branch_note"))
    }
    await FlowConfig.create_version(config)
    ctx = require_context()
    if ctx.active_company is None:
        raise AssertionError("active company required for flow authz sync")
    await di.flow_access_service.sync_flow_saved(
        config,
        company_id=ctx.active_company.company_id,
        owner_user_id=ctx.user.user_id,
    )


async def _session_branch(session_id: str, di) -> str:
    state = await di.workflow_runtime.get_state(session_id)
    assert state is not None, f"missing session {session_id}"
    return state.branch_id


@pytest.mark.asyncio
async def test_turn_projects_state_by_the_requested_branch_interface(
    client: AsyncClient,
    unique_id: str, di,
) -> None:
    flow_id = f"branch_ui_{unique_id}"
    branch_id = f"crm_{unique_id}"
    await _seed_branch_interface(flow_id=flow_id, branch_id=branch_id, di=di)

    branch_context = f"ctx-branch-{unique_id}"
    branch_task = await a2a_send(
        client,
        flow_id=flow_id,
        message=text_message(context_id=branch_context, text="hi"),
        branch_id=branch_id,
    )
    assert branch_task["contextId"] == branch_context
    assert branch_task["status"]["state"] == "TASK_STATE_COMPLETED", branch_task
    assert state_from_task(branch_task) == {"branch_note": "branch"}
    assert await _session_branch(f"{flow_id}:{branch_context}", di=di) == branch_id

    base_context = f"ctx-base-{unique_id}"
    base_task = await a2a_send(
        client,
        flow_id=flow_id,
        message=text_message(context_id=base_context, text="hi"),
        branch_id="default",
    )
    assert state_from_task(base_task) == {"base_note": "base"}
    assert await _session_branch(f"{flow_id}:{base_context}", di=di) == "default"


@pytest.mark.asyncio
async def test_turn_without_branch_metadata_uses_base(
    client: AsyncClient,
    unique_id: str, di,
) -> None:
    flow_id = f"branch_ui_default_{unique_id}"
    await _seed_branch_interface(flow_id=flow_id, branch_id=f"crm_{unique_id}", di=di)
    context_id = f"ctx-nobranch-{unique_id}"
    task = await a2a_send(
        client,
        flow_id=flow_id,
        message=text_message(context_id=context_id, text="hi"),
    )
    assert state_from_task(task) == {"base_note": "base"}
    assert await _session_branch(f"{flow_id}:{context_id}", di=di) == "default"


@pytest.mark.asyncio
async def test_second_branch_cannot_take_over_a_live_session(
    client: AsyncClient,
    unique_id: str, di,
) -> None:
    """Сессия владеет своей веткой: другая ветка на том же context отклоняется."""
    flow_id = f"branch_ui_takeover_{unique_id}"
    branch_id = f"crm_{unique_id}"
    other_branch_id = f"support_{unique_id}"
    await _seed_branch_interface(flow_id=flow_id, branch_id=branch_id, di=di)
    context_id = f"ctx-conflict-{unique_id}"
    _ = await a2a_send(
        client,
        flow_id=flow_id,
        message=text_message(context_id=context_id, text="hi"),
        branch_id=branch_id,
    )

    error = await a2a_send_error(
        client,
        flow_id=flow_id,
        message=text_message(context_id=context_id, text="again"),
        branch_id=other_branch_id,
    )
    assert other_branch_id in str(error), error
    assert await _session_branch(f"{flow_id}:{context_id}", di=di) == branch_id


@pytest.mark.asyncio
async def test_session_deep_link_without_branch_keeps_running_its_branch(
    client: AsyncClient,
    unique_id: str, di,
) -> None:
    """URL сессии может не нести ветку: ``default`` не сбрасывает сессию."""
    flow_id = f"branch_ui_deeplink_{unique_id}"
    branch_id = f"crm_{unique_id}"
    await _seed_branch_interface(flow_id=flow_id, branch_id=branch_id, di=di)
    context_id = f"ctx-deeplink-{unique_id}"
    _ = await a2a_send(
        client,
        flow_id=flow_id,
        message=text_message(context_id=context_id, text="hi"),
        branch_id=branch_id,
    )
    reopened = await a2a_send(
        client,
        flow_id=flow_id,
        message=text_message(context_id=context_id, text="again"),
        branch_id="default",
    )
    assert reopened["status"]["state"] == "TASK_STATE_COMPLETED", reopened
    assert state_from_task(reopened) == {"branch_note": "branch"}
    assert await _session_branch(f"{flow_id}:{context_id}", di=di) == branch_id
