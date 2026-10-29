"""llm_node + tool hitl_operator_task: single_reply и takeover. Без monkeypatch."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest
from a2a.helpers.proto_helpers import get_message_text
from httpx2 import AsyncClient

from apps.flows.di import FlowsDi
from core.clients.llm.mock import MockLLMQueuedResponse
from core.context import get_context, reset_context, set_context
from core.state import ExecutionState
from core.state.interrupt import HandoffMode, OperatorTaskInterrupt
from core.types import JsonObject
from core.worktracker.models import UserActor, WorkItem, WorkItemState
from tests.flows._a2a_v1 import A2A_HEADERS, SEND_MESSAGE, a2a_rpc, a2a_text_message
from tests.flows.durable_runtime_harness import run_flow, workflow_state
from tests.flows.hitl_test_harness import llm_hitl_flow_create_payload

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.timeout(180, func_only=True),
]

HITL_API = "/flows/api/v1/hitl"
WORK_ITEMS = "/worktracker/api/v1/work-items"

MockLlmRedis = Callable[[list[MockLLMQueuedResponse]], Awaitable[None]]


def _hitl_tool_call(*, queue_slug: str, mode: HandoffMode, unique_id: str) -> JsonObject:
    return {
        "type": "tool_call",
        "tool": "hitl_operator_task",
        "args": {
            "question": f"Нужен оператор {unique_id}",
            "task_title": f"HITL tool {unique_id}",
            "assignee_queue": queue_slug,
            "handoff_mode": mode.value,
        },
    }


def _message_texts(state: ExecutionState) -> list[str]:
    return [get_message_text(message) for message in state.messages]


def _task_interrupt_kind(task: object) -> str | None:
    if not isinstance(task, dict):
        raise AssertionError(f"A2A task must be object, got {type(task)}")
    status = task.get("status")
    if not isinstance(status, dict):
        return None
    message = status.get("message")
    metadata: object = {}
    if isinstance(message, dict) and isinstance(message.get("metadata"), dict):
        metadata = message["metadata"]
    elif isinstance(task.get("metadata"), dict):
        metadata = task["metadata"]
    if not isinstance(metadata, dict):
        return None
    interrupt = metadata.get("platform_interrupt")
    if not isinstance(interrupt, dict):
        return None
    body = interrupt.get("body")
    if not isinstance(body, dict):
        return None
    kind = body.get("kind")
    return kind if isinstance(kind, str) else None


async def _wait_state(
    di: FlowsDi,
    session_id: str,
    *,
    timeout_sec: float = 60.0,
) -> ExecutionState:
    deadline = asyncio.get_running_loop().time() + timeout_sec
    last_state: ExecutionState | None = None
    while asyncio.get_running_loop().time() < deadline:
        last_state = await di.workflow_runtime.get_state(session_id)
        if (
            last_state is not None
            and last_state.interrupt is None
            and last_state.response is not None
            and last_state.response.strip() != ""
        ):
            return last_state
        await asyncio.sleep(0.2)
    raise AssertionError(
        (
            f"HITL llm_node session {session_id!r} did not clear interrupt; "
            + f"interrupt={getattr(last_state, 'interrupt', None)!r} "
            + f"response={getattr(last_state, 'response', None)!r}"
        )
    )


async def _create_llm_hitl_flow(client: AsyncClient, *, flow_id: str) -> None:
    created = await client.post(
        "/flows/api/v1/flows/",
        headers=A2A_HEADERS,
        json=llm_hitl_flow_create_payload(flow_id=flow_id),
    )
    assert created.status_code == 200, created.text


async def _park_llm_hitl(
    di: FlowsDi,
    client: AsyncClient,
    unique_id: str,
    *,
    mode: HandoffMode,
    owner_user_id: str,
    mock_llm_redis: MockLlmRedis,
    extra_llm_responses: list[JsonObject] | None = None,
) -> tuple[ExecutionState, WorkItem, str]:
    queue_slug = f"hitl-llm-q-{unique_id}"
    current = get_context()
    if current is None:
        raise RuntimeError("HITL llm_node test requires Context")
    queue = await di.work_item_service.create_queue(
        company_id="system",
        name=f"HITL LLM {unique_id}",
        slug=queue_slug,
        creator=UserActor(user_id=owner_user_id),
    )
    _ = await di.work_item_service.add_queue_member(
        company_id="system",
        work_queue_id=queue.work_queue_id,
        member=UserActor(user_id=owner_user_id),
    )
    flow_id = f"hitl_llm_{unique_id}"
    await _create_llm_hitl_flow(client, flow_id=flow_id)
    queued: list[MockLLMQueuedResponse] = []
    if extra_llm_responses is not None:
        queued.extend(extra_llm_responses)
    queued.append(_hitl_tool_call(queue_slug=queue_slug, mode=mode, unique_id=unique_id))
    queued.append({"type": "text", "content": f"после оператора {unique_id}"})
    await mock_llm_redis(queued)
    state = workflow_state(
        flow_id=flow_id,
        unique_id=unique_id,
        content=f"эскалация {unique_id}",
        user_id=current.user.user_id,
    )
    flow = await di.flow_factory.get_flow(flow_id, tool_registry=di.tool_registry)
    if flow is None:
        raise RuntimeError(f"llm_node HITL flow {flow_id} missing after create")
    token = set_context(current.model_copy(update={"channel": "a2a"}))
    try:
        parked = await run_flow(di=di, flow=flow, state=state)
    finally:
        reset_context(token)
    assert parked.interrupt is not None
    assert isinstance(parked.interrupt.body, OperatorTaskInterrupt)
    assert parked.interrupt.body.handoff_mode == mode
    assert parked.interrupt.body.tool_call_id is not None
    assert parked.interrupt.body.node_id == "agent"
    assert parked.interrupt.correlation_id is not None
    item = await di.work_item_service.find_by_completion_correlation(
        "system", str(parked.interrupt.correlation_id)
    )
    assert item is not None
    assert item.state is WorkItemState.OPEN
    return parked, item, queue_slug


async def test_llm_node_calculator_then_hitl_single_reply_resumes_via_platform_events(
    app: object,
    di: FlowsDi,
    worktracker_di: object,
    client: AsyncClient,
    worktracker_client: AsyncClient,
    mock_llm_redis: MockLlmRedis,
    unique_id: str,
    system_user_id: str,
) -> None:
    _ = app
    _ = worktracker_di
    parked, item, _queue = await _park_llm_hitl(
        di,
        client,
        unique_id,
        mode=HandoffMode.SINGLE_REPLY,
        owner_user_id=system_user_id,
        mock_llm_redis=mock_llm_redis,
        extra_llm_responses=[
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "2+2"}},
        ],
    )
    assert "calculator" in parked.tool_results
    assert "4" in str(parked.tool_results["calculator"])
    reply = f"оператор {unique_id}"
    done = await worktracker_client.post(
        f"{WORK_ITEMS}/{item.work_item_id}/complete",
        json={"resolution_text": reply},
    )
    assert done.status_code == 200, done.text
    assert done.json()["state"] == "done"
    resumed = await _wait_state(di, parked.session_id)
    assert resumed.interrupt is None
    assert reply in _message_texts(resumed)
    assert resumed.response == reply


async def test_llm_node_hitl_takeover_user_append_operator_ask_then_empty_complete(
    app: object,
    di: FlowsDi,
    worktracker_di: object,
    client: AsyncClient,
    worktracker_client: AsyncClient,
    mock_llm_redis: MockLlmRedis,
    unique_id: str,
    system_user_id: str,
) -> None:
    _ = app
    _ = worktracker_di
    parked, item, _queue = await _park_llm_hitl(
        di,
        client,
        unique_id,
        mode=HandoffMode.TAKEOVER,
        owner_user_id=system_user_id,
        mock_llm_redis=mock_llm_redis,
    )
    user_text = f"покупатель {unique_id}"
    send = await client.post(
        f"/flows/api/v1/{parked.session_flow_id}",
        headers=A2A_HEADERS,
        json=a2a_rpc(
            SEND_MESSAGE,
            {
                "message": a2a_text_message(
                    user_text,
                    task_id=parked.task_id,
                    context_id=parked.context_id,
                )
            },
        ),
    )
    assert send.status_code == 200, send.text
    body = send.json()
    assert "error" not in body, body
    task = body["result"]
    assert task["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
    assert _task_interrupt_kind(task) == "operator_task"

    operator_text = f"уточнение {unique_id}"
    ask = await client.post(
        f"{HITL_API}/{item.work_item_id}/conversation/messages",
        json={"text": operator_text, "idempotency_key": f"ask-{unique_id}"},
    )
    assert ask.status_code == 200, ask.text
    assert ask.json()["role"] == "operator"
    assert ask.json()["text"] == operator_text

    snapshot = await client.get(f"{HITL_API}/{item.work_item_id}/conversation")
    assert snapshot.status_code == 200, snapshot.text
    turns = snapshot.json()["turns"]
    assert any(turn["role"] == "user" and turn["text"] == user_text for turn in turns)
    assert any(
        turn["role"] == "operator" and turn["text"] == operator_text for turn in turns
    )

    still_open = await WorkItem.require_in_company("system", item.work_item_id)
    assert still_open.state is WorkItemState.OPEN
    mid = await di.workflow_runtime.get_state(parked.session_id)
    assert mid is not None
    assert mid.interrupt is not None
    assert isinstance(mid.interrupt.body, OperatorTaskInterrupt)
    assert mid.interrupt.body.handoff_mode == HandoffMode.TAKEOVER
    assert mid.interrupt.body.tool_call_id is not None

    done = await worktracker_client.post(
        f"{WORK_ITEMS}/{item.work_item_id}/complete",
        json={"resolution_text": ""},
    )
    assert done.status_code == 200, done.text
    assert done.json()["state"] == "done"
    resumed = await _wait_state(di, parked.session_id)
    assert resumed.interrupt is None
    assert resumed.response is not None
    assert resumed.response.strip() != ""


async def test_a2a_send_parks_llm_node_hitl_operator_task(
    app: object,
    di: FlowsDi,
    worktracker_di: object,
    client: AsyncClient,
    mock_llm_redis: MockLlmRedis,
    unique_id: str,
    system_user_id: str,
) -> None:
    _ = app
    _ = worktracker_di
    queue_slug = f"hitl-a2a-q-{unique_id}"
    queue = await di.work_item_service.create_queue(
        company_id="system",
        name=f"HITL A2A {unique_id}",
        slug=queue_slug,
        creator=UserActor(user_id=system_user_id),
    )
    _ = await di.work_item_service.add_queue_member(
        company_id="system",
        work_queue_id=queue.work_queue_id,
        member=UserActor(user_id=system_user_id),
    )
    flow_id = f"hitl_llm_a2a_{unique_id}"
    await _create_llm_hitl_flow(client, flow_id=flow_id)
    await mock_llm_redis(
        [
            _hitl_tool_call(
                queue_slug=queue_slug,
                mode=HandoffMode.SINGLE_REPLY,
                unique_id=unique_id,
            )
        ]
    )
    context_id = f"ctx-a2a-{unique_id}"
    send = await client.post(
        f"/flows/api/v1/{flow_id}",
        headers=A2A_HEADERS,
        json=a2a_rpc(
            SEND_MESSAGE,
            {"message": a2a_text_message(f"нужен человек {unique_id}", context_id=context_id)},
        ),
    )
    assert send.status_code == 200, send.text
    body = send.json()
    assert "error" not in body, body
    task = body["result"]
    assert task["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
    assert _task_interrupt_kind(task) == "operator_task"
    session_id = f"{flow_id}:{context_id}"
    parked = await di.workflow_runtime.get_state(session_id)
    assert parked is not None
    assert parked.interrupt is not None
    assert isinstance(parked.interrupt.body, OperatorTaskInterrupt)
    assert parked.interrupt.body.tool_call_id is not None
    assert parked.interrupt.body.handoff_mode == HandoffMode.SINGLE_REPLY
    item = await di.work_item_service.find_by_completion_correlation(
        "system", str(parked.interrupt.correlation_id)
    )
    assert item is not None
    assert item.state is WorkItemState.OPEN
