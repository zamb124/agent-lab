"""Lara Sync E2E: MockLLM loads skills and exercises Sync employee tools via run_flow."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest
from httpx2 import AsyncClient
from pydantic import TypeAdapter

from apps.flows.di import FlowsDi
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.services.platform_assistant_skills import (
    LARA_PLATFORM_SKILL_ROOTS,
    PLATFORM_ASSISTANT_SEED_SKILL_IDS,
    seed_platform_assistant_skills,
)
from core.clients.llm.mock import MockLLM, MockLLMQueuedResponse
from core.context import clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.identity.flow_employee import ensure_flow_employee, flow_employee_user_id
from core.models.identity_models import Company, User
from core.state import ExecutionState
from core.types import JsonObject, JsonValue
from tests.flows.agent_skills_harness import ensure_lara_flow
from tests.flows.durable_runtime_harness import run_flow
from tests.sync.api._helpers import seed_namespace_via_repo

pytestmark = [pytest.mark.usefixtures("app"), pytest.mark.timeout(180, func_only=True)]

MockLLMQueue = Callable[[list[MockLLMQueuedResponse]], MockLLM]
_JSON_OBJECT_ADAPTER: TypeAdapter[JsonObject] = TypeAdapter(JsonObject)
_SYNC_BASE = "http://127.0.0.1:9005"
_BRANCH = "sync"


@contextmanager
def _employee_context(employee_user: User, company: Company) -> Iterator[None]:
    previous = get_context()
    set_context(
        build_job_context(
            company=company,
            user=employee_user,
            host="",
            trace_id="lara-sync-skills-runtime",
            session_id="lara-sync-skills",
            channel="a2a",
        )
    )
    try:
        yield
    finally:
        if previous is None:
            clear_context()
        else:
            set_context(previous)


def _lara_state(*, unique_id: str, user_id: str, suffix: str = "") -> ExecutionState:
    context_id = f"lara-sync-{unique_id}{suffix}"
    return ExecutionState(
        task_id=f"task-sync-{unique_id}{suffix}",
        context_id=context_id,
        user_id=user_id,
        session_id=f"lara:{context_id}",
        branch_id=_BRANCH,
        content=f"sync runtime {unique_id}{suffix}",
    )


async def _seed_lara_skills(di: FlowsDi) -> None:
    seeded = await seed_platform_assistant_skills(
        di.files_service,
        "system",
    )
    assert seeded == len(PLATFORM_ASSISTANT_SEED_SKILL_IDS)


async def _require_lara(di: FlowsDi) -> Flow:
    _ = await ensure_lara_flow(di)
    flow = await di.flow_factory.get_flow("lara", branch_id=_BRANCH, tool_registry=di.tool_registry)
    assert flow is not None
    return flow


async def _run_lara(di: FlowsDi, *, state: ExecutionState) -> ExecutionState:
    flow = await _require_lara(di)
    main_node = flow.nodes["main"]
    assert getattr(main_node, "agent_skill_ids", None) == list(LARA_PLATFORM_SKILL_ROOTS)
    tool_names = {tool.name for tool in await main_node.get_tools(state)}
    assert "load_agent_skill" in tool_names
    assert "sync_list_messages" not in tool_names
    return await run_flow(
        di=di,
        flow=flow,
        state=state,
    )


def _tool_json(value: JsonValue) -> JsonObject:
    if isinstance(value, str):
        return _JSON_OBJECT_ADAPTER.validate_json(value)
    return _JSON_OBJECT_ADAPTER.validate_python(value)


def _captured_tool_names(call: JsonObject) -> set[str]:
    raw_tools = call.get("tools")
    names: set[str] = set()
    if not isinstance(raw_tools, list):
        return names
    for tool in raw_tools:
        if not isinstance(tool, dict):
            continue
        direct_name = tool.get("name")
        if isinstance(direct_name, str) and direct_name.strip():
            names.add(direct_name)
            continue
        function = tool.get("function")
        if isinstance(function, dict):
            function_name = function.get("name")
            if isinstance(function_name, str) and function_name.strip():
                names.add(function_name)
    return names


def _load(*skill_ids: str) -> list[MockLLMQueuedResponse]:
    return [
        {
            "type": "tool_call",
            "tool": "load_agent_skill",
            "args": {"agent_skill_id": skill_id},
        }
        for skill_id in skill_ids
    ]


def _text(content: str) -> MockLLMQueuedResponse:
    return {"type": "text", "content": content}


def _call(tool: str, **args: object) -> MockLLMQueuedResponse:
    return {"type": "tool_call", "tool": tool, "args": dict(args)}


async def _prepare_employee_channel(
    *,
    frontend_di,
    auth_token_system: str,
    unique_id: str,
    flow_suffix: str,
) -> tuple[User, Company, str, str, str]:
    flow_id = f"lara_sync_{flow_suffix}_{unique_id}"
    company = await Company.get("system")
    assert company is not None
    employee = await ensure_flow_employee(
        frontend_di,
        flow_id=flow_id,
        company_id="system",
        name=f"Lara Sync {flow_suffix}",
        roles=["member"],
        curator_user_ids=["system"],
    )
    employee_user_id = flow_employee_user_id(flow_id)
    namespace = f"lara_sync_{flow_suffix}_{unique_id}"
    await seed_namespace_via_repo(frontend_di, "system", namespace)
    headers = {"Authorization": f"Bearer {auth_token_system}"}
    async with AsyncClient(base_url=_SYNC_BASE, timeout=60.0) as http:
        created = await http.post(
            "/sync/api/v1/channels/",
            headers=headers,
            json={
                "namespace": namespace,
                "type": "topic",
                "name": f"lara {flow_suffix}",
                "is_private": False,
            },
        )
        assert created.status_code == 201, created.text
        channel_id = created.json()["channel_id"]
        member_added = await http.post(
            f"/sync/api/v1/channels/{channel_id}/members",
            headers=headers,
            json={"user_id": employee_user_id, "role": "member"},
        )
        assert member_added.status_code in (200, 201), member_added.text
    return employee, company, employee_user_id, channel_id, namespace


@pytest.mark.asyncio
async def test_lara_sync_skill_unlocks_tools_after_load(
    di: FlowsDi,
    flows_service,
    sync_service,
    frontend_di,
    auth_token_system: str,
    mock_llm_with_queue: MockLLMQueue,
    mock_llm_capture,
    unique_id: str,
) -> None:
    _ = flows_service, sync_service
    employee, company, employee_user_id, _channel_id, _ns = await _prepare_employee_channel(
        frontend_di=frontend_di,
        auth_token_system=auth_token_system,
        unique_id=unique_id,
        flow_suffix="unlock",
    )
    _ = mock_llm_with_queue(
        [
            *_load(
                "sync-platform",
                "sync-messaging",
                "sync-channels",
                "sync-threads",
                "team-directory",
            ),
            _text(f"skills ready {unique_id}"),
        ]
    )
    state = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-unlock")
    with _employee_context(employee, company):
        await _seed_lara_skills(di)
        result = await _run_lara(di, state=state)

    assert result.interrupt is None
    calls = await mock_llm_capture()
    assert "sync_list_messages" not in _captured_tool_names(calls[0])
    unlocked = set().union(*(_captured_tool_names(call) for call in calls))
    for tool_name in (
        "sync_list_messages",
        "sync_send_message",
        "sync_list_channels",
        "sync_list_threads",
        "team_resolve_user",
    ):
        assert tool_name in unlocked


@pytest.mark.asyncio
async def test_lara_sync_messaging_lifecycle(
    di: FlowsDi,
    flows_service,
    sync_service,
    frontend_di,
    auth_token_system: str,
    system_user_id: str,
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    _ = flows_service, sync_service
    employee, company, employee_user_id, channel_id, _ns = await _prepare_employee_channel(
        frontend_di=frontend_di,
        auth_token_system=auth_token_system,
        unique_id=unique_id,
        flow_suffix="msg",
    )
    text = f"lifecycle {unique_id}"
    _ = mock_llm_with_queue(
        [
            *_load("sync-platform", "sync-messaging", "sync-channels", "team-directory"),
            _call("sync_list_channels"),
            _call("sync_list_channel_members", channel_id=channel_id),
            _call("sync_send_message", channel_id=channel_id, text=text),
            _call("sync_list_messages", channel_id=channel_id, limit=20),
            _text("created"),
        ]
    )
    state1 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-m1")
    with _employee_context(employee, company):
        await _seed_lara_skills(di)
        result1 = await _run_lara(di, state=state1)

    assert result1.interrupt is None
    channels = _tool_json(result1.tool_results["sync_list_channels"])
    assert any(
        isinstance(row, dict) and row.get("channel_id") == channel_id
        for row in channels["items"]
    )
    members = _tool_json(result1.tool_results["sync_list_channel_members"])
    assert any(
        isinstance(row, dict) and row.get("user_id") == employee_user_id
        for row in members["items"]
    )
    sent = _tool_json(result1.tool_results["sync_send_message"])
    message_id = sent["message_id"]
    assert isinstance(message_id, str) and message_id
    listed = _tool_json(result1.tool_results["sync_list_messages"])
    assert int(listed["count"]) >= 1

    _ = mock_llm_with_queue(
        [
            *_load("sync-platform", "sync-messaging", "sync-channels", "team-directory"),
            _call(
                "sync_edit_message",
                channel_id=channel_id,
                message_id=message_id,
                text=f"{text} edited",
            ),
            _call(
                "sync_react_message",
                channel_id=channel_id,
                message_id=message_id,
                emoji="👍",
            ),
            _call(
                "sync_send_message",
                channel_id=channel_id,
                text=f"mention {unique_id}",
                mentioned_user_ids=[system_user_id],
            ),
            _call("sync_mark_message_read", channel_id=channel_id, message_id=message_id),
            _call("sync_mark_channel_read", channel_id=channel_id),
            _text("lifecycle done"),
        ]
    )
    state2 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-m2")
    with _employee_context(employee, company):
        result2 = await _run_lara(di, state=state2)

    assert result2.interrupt is None
    edited = _tool_json(result2.tool_results["sync_edit_message"])
    assert "edited" in str(edited.get("text_preview"))
    reacted = _tool_json(result2.tool_results["sync_react_message"])
    assert reacted["message_id"] == message_id
    mentioned = _tool_json(result2.tool_results["sync_send_message"])
    assert isinstance(mentioned["message_id"], str)
    assert _tool_json(result2.tool_results["sync_mark_message_read"])["read"] is True
    assert _tool_json(result2.tool_results["sync_mark_channel_read"])["read"] is True


@pytest.mark.asyncio
async def test_lara_sync_channels_create_update_mute_delete(
    di: FlowsDi,
    flows_service,
    sync_service,
    frontend_di,
    auth_token_system: str,
    system_user_id: str,
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    _ = flows_service, sync_service
    employee, company, employee_user_id, _seed_channel_id, namespace = (
        await _prepare_employee_channel(
            frontend_di=frontend_di,
            auth_token_system=auth_token_system,
            unique_id=unique_id,
            flow_suffix="ch",
        )
    )
    _ = mock_llm_with_queue(
        [
            *_load("sync-platform", "sync-channels", "sync-messaging", "team-directory"),
            _call(
                "sync_create_channel",
                type="topic",
                name=f"topic-{unique_id}",
                namespace=namespace,
            ),
            _call(
                "sync_create_channel",
                type="direct",
                member_ids=[system_user_id],
            ),
            _text("channels created"),
        ]
    )
    state1 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-c1")
    with _employee_context(employee, company):
        await _seed_lara_skills(di)
        result1 = await _run_lara(di, state=state1)

    assert result1.interrupt is None
    dm = _tool_json(result1.tool_results["sync_create_channel"])
    assert isinstance(dm.get("channel_id"), str)

    # Create topic as employee for update/add/mute (employee is owner).
    _ = mock_llm_with_queue(
        [
            *_load("sync-platform", "sync-channels", "sync-messaging"),
            _call(
                "sync_create_channel",
                type="topic",
                name=f"owned-{unique_id}",
                namespace=namespace,
            ),
            _text("owned topic"),
        ]
    )
    state_own = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-cown")
    with _employee_context(employee, company):
        result_own = await _run_lara(di, state=state_own)

    assert result_own.interrupt is None
    owned = _tool_json(result_own.tool_results["sync_create_channel"])
    channel_id = owned["channel_id"]
    assert isinstance(channel_id, str)

    _ = mock_llm_with_queue(
        [
            *_load("sync-platform", "sync-channels", "sync-messaging"),
            _call(
                "sync_update_channel",
                channel_id=channel_id,
                name=f"renamed-{unique_id}",
            ),
            _call(
                "sync_add_channel_member",
                channel_id=channel_id,
                user_id=system_user_id,
                role="member",
            ),
            _call(
                "sync_channel_notification_settings",
                channel_id=channel_id,
                notifications_muted=True,
            ),
            _call("sync_send_message", channel_id=channel_id, text=f"to-delete-{unique_id}"),
            _text("updated"),
        ]
    )
    state2 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-c2")
    with _employee_context(employee, company):
        result2 = await _run_lara(di, state=state2)

    assert result2.interrupt is None
    updated = _tool_json(result2.tool_results["sync_update_channel"])
    assert updated.get("name") == f"renamed-{unique_id}"
    added = _tool_json(result2.tool_results["sync_add_channel_member"])
    assert added.get("user_id") == system_user_id
    muted = _tool_json(result2.tool_results["sync_channel_notification_settings"])
    assert muted.get("notifications_muted") is True
    to_delete = _tool_json(result2.tool_results["sync_send_message"])
    delete_id = to_delete["message_id"]
    assert isinstance(delete_id, str)

    _ = mock_llm_with_queue(
        [
            *_load("sync-platform", "sync-messaging", "team-directory"),
            _call(
                "sync_delete_message",
                channel_id=channel_id,
                message_id=delete_id,
            ),
            _call("team_list_members"),
            _text("deleted"),
        ]
    )
    state3 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-c3")
    with _employee_context(employee, company):
        result3 = await _run_lara(di, state=state3)

    assert result3.interrupt is None
    deleted = _tool_json(result3.tool_results["sync_delete_message"])
    assert deleted.get("deleted") is True
    team = _tool_json(result3.tool_results["team_list_members"])
    assert isinstance(team["items"], list) and team["items"]


@pytest.mark.asyncio
async def test_lara_sync_threads_flow(
    di: FlowsDi,
    flows_service,
    sync_service,
    frontend_di,
    auth_token_system: str,
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    _ = flows_service, sync_service
    employee, company, employee_user_id, channel_id, _ns = await _prepare_employee_channel(
        frontend_di=frontend_di,
        auth_token_system=auth_token_system,
        unique_id=unique_id,
        flow_suffix="th",
    )
    _ = mock_llm_with_queue(
        [
            *_load("sync-platform", "sync-messaging", "sync-threads"),
            _call(
                "sync_send_message",
                channel_id=channel_id,
                text=f"root-{unique_id}",
            ),
            _text("root sent"),
        ]
    )
    state1 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-t1")
    with _employee_context(employee, company):
        await _seed_lara_skills(di)
        result1 = await _run_lara(di, state=state1)

    assert result1.interrupt is None
    root = _tool_json(result1.tool_results["sync_send_message"])
    root_message_id = root["message_id"]
    assert isinstance(root_message_id, str)

    _ = mock_llm_with_queue(
        [
            *_load("sync-platform", "sync-messaging", "sync-threads"),
            _call(
                "sync_create_thread",
                channel_id=channel_id,
                root_message_id=root_message_id,
                title=f"thread-{unique_id}",
            ),
            _call("sync_list_threads", channel_id=channel_id),
            _text("thread created"),
        ]
    )
    state2 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-t2")
    with _employee_context(employee, company):
        result2 = await _run_lara(di, state=state2)

    assert result2.interrupt is None
    thread = _tool_json(result2.tool_results["sync_create_thread"])
    thread_id = thread["thread_id"]
    assert isinstance(thread_id, str) and thread_id
    threads = _tool_json(result2.tool_results["sync_list_threads"])
    assert any(
        isinstance(row, dict) and row.get("thread_id") == thread_id
        for row in threads["items"]
    )

    _ = mock_llm_with_queue(
        [
            *_load("sync-platform", "sync-messaging", "sync-threads"),
            _call("sync_get_thread", thread_id=thread_id),
            _call(
                "sync_send_message",
                channel_id=channel_id,
                text=f"in-thread-{unique_id}",
                thread_id=thread_id,
            ),
            _call(
                "sync_list_thread_messages",
                channel_id=channel_id,
                thread_id=thread_id,
            ),
            _text("thread messages"),
        ]
    )
    state3 = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix="-t3")
    with _employee_context(employee, company):
        result3 = await _run_lara(di, state=state3)

    assert result3.interrupt is None
    got = _tool_json(result3.tool_results["sync_get_thread"])
    assert got["thread_id"] == thread_id
    reply = _tool_json(result3.tool_results["sync_send_message"])
    assert isinstance(reply["message_id"], str)
    thread_msgs = _tool_json(result3.tool_results["sync_list_thread_messages"])
    assert int(thread_msgs["count"]) >= 1
    assert any(
        isinstance(row, dict) and f"in-thread-{unique_id}" in str(row.get("text_preview"))
        for row in thread_msgs["items"]
    )
