"""HITL resume через шину platform:events + flows_worker. Без AsyncMock."""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from apps.flows.src.models.flow_config import FlowConfig
from core.context import get_context, reset_context, set_context
from core.state.interrupt import HandoffMode, OperatorTaskInterrupt
from core.worktracker.models import UserActor
from tests.flows.durable_runtime_harness import run_flow, workflow_state
from tests.flows.hitl_test_harness import hitl_flow_create_payload

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.timeout(180, func_only=True),
]

WORK_ITEMS = "/worktracker/api/v1/work-items"


async def _wait_hitl_resumed(
    container,
    session_id: str,
    *,
    needle: str,
    timeout_sec: float = 60.0,
):
    deadline = asyncio.get_running_loop().time() + timeout_sec
    last_state = None
    while asyncio.get_running_loop().time() < deadline:
        last_state = await container.workflow_runtime.get_state(session_id)
        if (
            last_state is not None
            and last_state.interrupt is None
            and needle in str(last_state.response or "")
        ):
            return last_state
        await asyncio.sleep(0.2)
    raise AssertionError(
        f"HITL session {session_id!r} did not resume with {needle!r}; "
        f"interrupt={getattr(last_state, 'interrupt', None)!r} "
        f"response={getattr(last_state, 'response', None)!r}"
    )


async def _park_real_hitl_flow(
    container,
    unique_id: str,
    *,
    mode: HandoffMode,
    owner_user_id: str,
):
    queue_slug = f"hitl-q-{unique_id}"
    await container.work_item_service.create_queue(
        company_id="system",
        name=f"HITL {unique_id}",
        slug=queue_slug,
        creator=UserActor(user_id=owner_user_id),
    )
    flow_id = f"hitl_resume_{unique_id}"
    await container.flow_repository.set(
        FlowConfig.model_validate(
            hitl_flow_create_payload(
                flow_id=flow_id, queue_slug=queue_slug, mode=mode
            )
        )
    )
    current = get_context()
    if current is None:
        raise RuntimeError("HITL resume test requires Context")
    state = workflow_state(
        flow_id=flow_id,
        unique_id=unique_id,
        content="need operator",
        user_id=current.user.user_id,
    )
    flow = await container.flow_factory.get_flow(flow_id)
    token = set_context(current.model_copy(update={"channel": "a2a"}))
    try:
        parked = await run_flow(container=container, flow=flow, state=state)
    finally:
        reset_context(token)
    assert parked.interrupt is not None
    assert isinstance(parked.interrupt.body, OperatorTaskInterrupt)
    assert parked.interrupt.correlation_id is not None
    item = await container.work_item_service.find_by_completion_correlation(
        "system", str(parked.interrupt.correlation_id)
    )
    assert item is not None
    return parked, item


async def _wait_hitl_interrupt_cleared(
    container,
    session_id: str,
    *,
    timeout_sec: float = 60.0,
):
    deadline = asyncio.get_running_loop().time() + timeout_sec
    last_state = None
    while asyncio.get_running_loop().time() < deadline:
        last_state = await container.workflow_runtime.get_state(session_id)
        if last_state is not None and last_state.interrupt is None:
            return last_state
        await asyncio.sleep(0.2)
    raise AssertionError(
        f"HITL session {session_id!r} did not clear interrupt; "
        f"interrupt={getattr(last_state, 'interrupt', None)!r} "
        f"response={getattr(last_state, 'response', None)!r}"
    )


async def test_single_reply_complete_resumes_via_platform_events(
    app,
    container,
    worktracker_container,
    worktracker_client: AsyncClient,
    unique_id: str,
    system_user_id: str,
) -> None:
    _ = app
    _ = worktracker_container
    parked, item = await _park_real_hitl_flow(
        container,
        unique_id,
        mode=HandoffMode.SINGLE_REPLY,
        owner_user_id=system_user_id,
    )
    reply = f"оператор {unique_id}"
    done = await worktracker_client.post(
        f"{WORK_ITEMS}/{item.work_item_id}/complete",
        json={"resolution_text": reply},
    )
    assert done.status_code == 200, done.text
    assert done.json()["state"] == "done"
    resumed = await _wait_hitl_resumed(container, parked.session_id, needle=reply)
    assert resumed.interrupt is None
    assert resumed.response == reply


async def test_takeover_complete_empty_resumes_via_platform_events(
    app,
    container,
    worktracker_container,
    worktracker_client: AsyncClient,
    unique_id: str,
    system_user_id: str,
) -> None:
    _ = app
    _ = worktracker_container
    parked, item = await _park_real_hitl_flow(
        container,
        unique_id,
        mode=HandoffMode.TAKEOVER,
        owner_user_id=system_user_id,
    )
    done = await worktracker_client.post(
        f"{WORK_ITEMS}/{item.work_item_id}/complete",
        json={"resolution_text": ""},
    )
    assert done.status_code == 200, done.text
    assert done.json()["state"] == "done"
    resumed = await _wait_hitl_interrupt_cleared(container, parked.session_id)
    assert resumed.interrupt is None
