"""Lara worktracker E2E: MockLLM loads skills and exercises every Worktracker tool scenario."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import TypeAdapter

from apps.flows.di import FlowsDi
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.services.platform_assistant_skills import (
    LARA_PLATFORM_SKILL_ROOTS,
    PLATFORM_ASSISTANT_SEED_SKILL_IDS,
    seed_platform_assistant_skills,
)
from apps.flows.src.state import ExecutionState
from core.clients.llm.mock import MockLLM, MockLLMQueuedResponse
from core.context import clear_context, get_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User
from core.types import JsonObject, JsonValue
from core.worktracker.models import (
    QueueAssignment,
    UserActor,
    UsersAssignment,
    WorkItem,
    WorkItemState,
)
from tests.fixtures.auth import service_client_asgi_auth_context
from tests.flows.agent_skills_harness import ensure_lara_flow
from tests.flows.durable_runtime_harness import run_flow

pytestmark = [pytest.mark.usefixtures("app"), pytest.mark.timeout(180, func_only=True)]

MockLLMQueue = Callable[[list[MockLLMQueuedResponse]], MockLLM]
_JSON_OBJECT_ADAPTER: TypeAdapter[JsonObject] = TypeAdapter(JsonObject)

_BRANCH = "worktracker"


@contextmanager
def _system_context(*, auth_token: str, system_user_id: str) -> Iterator[None]:
    previous = get_context()
    set_context(
        Context(
            user=User(user_id=system_user_id, name="Lara worktracker runtime"),
            active_company=Company(company_id="system", name="System"),
            auth_token=auth_token,
            channel="test",
            active_namespace="default",
            metadata={"user_id": system_user_id, "email": "test@example.com", "grps": []},
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
    context_id = f"lara-wt-{unique_id}{suffix}"
    return ExecutionState(
        task_id=f"task-wt-{unique_id}{suffix}",
        context_id=context_id,
        user_id=user_id,
        session_id=f"lara:{context_id}",
        branch_id=_BRANCH,
        content=f"worktracker runtime {unique_id}{suffix}",
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


async def _run_lara(
    di: FlowsDi,
    *,
    state: ExecutionState,
) -> ExecutionState:
    flow = await _require_lara(di)
    main_node = flow.nodes["main"]
    assert getattr(main_node, "agent_skill_ids", None) == list(LARA_PLATFORM_SKILL_ROOTS)
    tool_names = {tool.name for tool in await main_node.get_tools(state)}
    assert "load_agent_skill" in tool_names
    assert "work_item_list_mine" not in tool_names
    return await run_flow(
        di=di,
        flow=flow,
        state=state,
    )


def _tool_json(value: JsonValue) -> JsonObject:
    if isinstance(value, str):
        return _JSON_OBJECT_ADAPTER.validate_json(value)
    return _JSON_OBJECT_ADAPTER.validate_python(value)


def _schedule_task_id_from_tool_result(value: JsonValue) -> str:
    payload = _tool_json(value)
    schedule_task_id = payload.get("schedule_task_id")
    if not isinstance(schedule_task_id, str) or not schedule_task_id.strip():
        raise AssertionError(f"schedule_task_id missing in tool result: {payload!r}")
    return schedule_task_id


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


@pytest.mark.asyncio
async def test_lara_worktracker_skill_unlocks_tools_after_load(
    di: FlowsDi,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    system_user_id: str,
    mock_llm_with_queue: MockLLMQueue,
    mock_llm_capture,
    unique_id: str,
) -> None:
    _ = mock_llm_with_queue(
        [
            *_load(
                "worktracker-platform",
                "work-tracking",
                "work-items",
                "work-queues",
                "work-boards",
                "team-directory",
            ),
            _text(f"skills ready {unique_id}"),
        ]
    )
    state = _lara_state(unique_id=unique_id, user_id=system_user_id, suffix="-unlock")
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            await _seed_lara_skills(di)
            result = await _run_lara(di, state=state)

    assert result.interrupt is None
    calls = await mock_llm_capture()
    assert "work_item_list_mine" not in _captured_tool_names(calls[0])
    unlocked = set().union(*(_captured_tool_names(call) for call in calls))
    for tool_name in (
        "work_item_list_mine",
        "work_item_get",
        "work_item_assign",
        "work_queue_list",
        "work_board_list",
        "team_resolve_user",
    ):
        assert tool_name in unlocked


@pytest.mark.asyncio
async def test_lara_worktracker_create_list_mine_get_update_comment_complete(
    di: FlowsDi,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    system_user_id: str,
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    title = f"Lara WI lifecycle {unique_id}"
    _ = mock_llm_with_queue(
        [
            *_load("worktracker-platform", "work-tracking", "team-directory"),
            _call(
                "work_item_create",
                title=title,
                description="phase-1 body",
                assignee_type="user",
                assignee_user_id=system_user_id,
                priority="high",
            ),
            _call("work_item_list_mine"),
            _text("created"),
        ]
    )
    state1 = _lara_state(unique_id=unique_id, user_id=system_user_id, suffix="-c1")
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            await _seed_lara_skills(di)
            result1 = await _run_lara(di, state=state1)

    assert result1.interrupt is None
    created = _tool_json(result1.tool_results["work_item_create"])
    work_item_id = created["work_item_id"]
    assert isinstance(work_item_id, str) and work_item_id
    assert created.get("board_id")
    mine = _tool_json(result1.tool_results["work_item_list_mine"])
    mine_ids = {
        item["work_item_id"]
        for item in mine["items"]
        if isinstance(item, dict) and isinstance(item.get("work_item_id"), str)
    }
    assert work_item_id in mine_ids
    assert mine.get("assignee_user_id") == system_user_id

    item = await WorkItem.require_in_company("system", work_item_id)
    assert item.title == title
    assert item.board_id is not None

    _ = mock_llm_with_queue(
        [
            *_load("worktracker-platform", "work-tracking", "work-items"),
            _call("work_item_get", work_item_id=work_item_id),
            _call(
                "work_item_update",
                work_item_id=work_item_id,
                title=f"{title} updated",
                description="phase-2 body",
                priority="urgent",
            ),
            _call("work_item_add_comment", work_item_id=work_item_id, text=f"note {unique_id}"),
            _call("work_item_list_comments", work_item_id=work_item_id),
            _call("work_item_mine_summary"),
            _call(
                "work_item_complete",
                work_item_id=work_item_id,
                resolution_text=f"done {unique_id}",
                terminal_state="done",
            ),
            _text("lifecycle done"),
        ]
    )
    state2 = _lara_state(unique_id=unique_id, user_id=system_user_id, suffix="-c2")
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            result2 = await _run_lara(di, state=state2)

    assert result2.interrupt is None
    detail = _tool_json(result2.tool_results["work_item_get"])
    assert detail["work_item_id"] == work_item_id
    assert detail["description"] == "phase-1 body"
    updated = _tool_json(result2.tool_results["work_item_update"])
    assert updated["title"] == f"{title} updated"
    assert updated["priority"] == "urgent"
    comments = _tool_json(result2.tool_results["work_item_list_comments"])
    assert any(
        isinstance(c, dict) and c.get("text") == f"note {unique_id}" for c in comments["items"]
    )
    summary = _tool_json(result2.tool_results["work_item_mine_summary"])
    assert "assigned_open_count" in summary
    assert "work_queue_ids" in summary
    completed = _tool_json(result2.tool_results["work_item_complete"])
    assert completed["state"] == WorkItemState.DONE.value
    persisted = await WorkItem.require_in_company("system", work_item_id)
    assert persisted.state == WorkItemState.DONE
    assert persisted.resolution is not None
    assert persisted.resolution.text == f"done {unique_id}"


@pytest.mark.asyncio
async def test_lara_worktracker_list_filters_assign_cancel_failed(
    di: FlowsDi,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    system_user_id: str,
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    open_item = await di.work_item_service.create_manual_task(
        company_id="system",
        title=f"open-filter-{unique_id}",
        created_by=UserActor(user_id=system_user_id),
        assignment=UsersAssignment(user_ids=[system_user_id]),
    )
    cancel_item = await di.work_item_service.create_manual_task(
        company_id="system",
        title=f"cancel-me-{unique_id}",
        created_by=UserActor(user_id=system_user_id),
        assignment=UsersAssignment(user_ids=[system_user_id]),
    )
    fail_item = await di.work_item_service.create_manual_task(
        company_id="system",
        title=f"fail-me-{unique_id}",
        created_by=UserActor(user_id=system_user_id),
        assignment=UsersAssignment(user_ids=[system_user_id]),
    )
    other_user = f"other_wt_{unique_id}"

    _ = mock_llm_with_queue(
        [
            *_load("worktracker-platform", "work-tracking", "work-items"),
            _call("work_item_list", state_filter="open", exclude_terminal=True, limit=100),
            _call(
                "work_item_assign",
                work_item_id=open_item.work_item_id,
                assignee_type="user",
                assignee_user_id=other_user,
            ),
            _call("work_item_cancel", work_item_id=cancel_item.work_item_id),
            _call(
                "work_item_complete",
                work_item_id=fail_item.work_item_id,
                resolution_text="failed path",
                terminal_state="failed",
            ),
            _text("filters assign cancel fail"),
        ]
    )
    state = _lara_state(unique_id=unique_id, user_id=system_user_id, suffix="-fac")
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            await _seed_lara_skills(di)
            result = await _run_lara(di, state=state)

    assert result.interrupt is None
    listed = _tool_json(result.tool_results["work_item_list"])
    listed_ids = {
        item["work_item_id"]
        for item in listed["items"]
        if isinstance(item, dict) and isinstance(item.get("work_item_id"), str)
    }
    assert open_item.work_item_id in listed_ids
    assigned = _tool_json(result.tool_results["work_item_assign"])
    assert assigned["work_item_id"] == open_item.work_item_id
    cancelled = _tool_json(result.tool_results["work_item_cancel"])
    assert cancelled["state"] == WorkItemState.CANCELLED.value
    failed = _tool_json(result.tool_results["work_item_complete"])
    assert failed["state"] == WorkItemState.FAILED.value

    persisted_open = await WorkItem.require_in_company("system", open_item.work_item_id)
    assert isinstance(persisted_open.assignment, UsersAssignment)
    assert persisted_open.assignment.user_ids == [other_user]
    assert (
        await WorkItem.require_in_company("system", cancel_item.work_item_id)
    ).state == WorkItemState.CANCELLED
    assert (
        await WorkItem.require_in_company("system", fail_item.work_item_id)
    ).state == WorkItemState.FAILED

    _ = mock_llm_with_queue(
        [
            *_load("worktracker-platform", "team-directory"),
            _call("team_list_members"),
            _text("team list"),
        ]
    )
    state2 = _lara_state(unique_id=unique_id, user_id=system_user_id, suffix="-fac2")
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            result2 = await _run_lara(di, state=state2)

    assert result2.interrupt is None
    members = _tool_json(result2.tool_results["team_list_members"])
    assert isinstance(members["items"], list) and members["items"]
    self_row = next(
        row
        for row in members["items"]
        if isinstance(row, dict) and row.get("user_id") == system_user_id
    )
    resolve_query = self_row.get("email") or self_row.get("name")
    assert isinstance(resolve_query, str) and resolve_query.strip()

    _ = mock_llm_with_queue(
        [
            *_load("worktracker-platform", "team-directory"),
            _call("team_resolve_user", query=resolve_query, limit=10),
            _text("team resolve"),
        ]
    )
    state3 = _lara_state(unique_id=unique_id, user_id=system_user_id, suffix="-fac3")
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            result3 = await _run_lara(di, state=state3)

    assert result3.interrupt is None
    resolved = _tool_json(result3.tool_results["team_resolve_user"])
    assert int(resolved["match_count"]) >= 1
    assert any(
        isinstance(row, dict) and row.get("user_id") == system_user_id
        for row in resolved["matches"]
    )


@pytest.mark.asyncio
async def test_lara_worktracker_queues_claim_and_members(
    di: FlowsDi,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    system_user_id: str,
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    slug = f"lara_wq_{unique_id}"
    member_id = f"wq_member_{unique_id}"

    _ = mock_llm_with_queue(
        [
            *_load(
                "worktracker-platform",
                "work-tracking",
                "work-items",
                "work-queues",
                "team-directory",
            ),
            _call(
                "work_queue_create",
                name=f"Lara Queue {unique_id}",
                work_queue_slug=slug,
                description="runtime queue",
            ),
            _call("work_queue_list"),
            _call("work_queue_get_by_slug", work_queue_slug=slug),
            _text("queue created"),
        ]
    )
    state1 = _lara_state(unique_id=unique_id, user_id=system_user_id, suffix="-q1")
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            await _seed_lara_skills(di)
            result1 = await _run_lara(di, state=state1)

    assert result1.interrupt is None
    queue = _tool_json(result1.tool_results["work_queue_create"])
    work_queue_id = queue["work_queue_id"]
    assert isinstance(work_queue_id, str) and work_queue_id
    assert queue["work_queue_slug"] == slug
    listed = _tool_json(result1.tool_results["work_queue_list"])
    assert any(
        isinstance(row, dict) and row.get("work_queue_id") == work_queue_id
        for row in listed["items"]
    )
    by_slug = _tool_json(result1.tool_results["work_queue_get_by_slug"])
    assert by_slug["work_queue_id"] == work_queue_id

    _ = mock_llm_with_queue(
        [
            *_load(
                "worktracker-platform",
                "work-tracking",
                "work-items",
                "work-queues",
                "team-directory",
            ),
            _call(
                "work_queue_update",
                work_queue_id=work_queue_id,
                name=f"Lara Queue {unique_id} upd",
                description="updated",
            ),
            _call(
                "work_queue_add_member",
                work_queue_id=work_queue_id,
                user_id=member_id,
                role="member",
            ),
            _call("work_queue_list_members", work_queue_id=work_queue_id),
            _call(
                "work_item_create",
                title=f"queue task {unique_id}",
                assignee_type="queue",
                assignee_queue_slug=slug,
            ),
            _text("queue members + task"),
        ]
    )
    state2 = _lara_state(unique_id=unique_id, user_id=system_user_id, suffix="-q2")
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            result2 = await _run_lara(di, state=state2)

    assert result2.interrupt is None
    updated_queue = _tool_json(result2.tool_results["work_queue_update"])
    assert updated_queue["name"] == f"Lara Queue {unique_id} upd"
    members = _tool_json(result2.tool_results["work_queue_list_members"])
    member_ids = {
        row["user_id"]
        for row in members["items"]
        if isinstance(row, dict) and isinstance(row.get("user_id"), str)
    }
    assert system_user_id in member_ids
    assert member_id in member_ids
    created = _tool_json(result2.tool_results["work_item_create"])
    claim_work_item_id = created["work_item_id"]
    assert isinstance(claim_work_item_id, str)

    queued = await WorkItem.require_in_company("system", claim_work_item_id)
    assert isinstance(queued.assignment, QueueAssignment)
    assert queued.assignment.work_queue_id == work_queue_id

    _ = mock_llm_with_queue(
        [
            *_load("worktracker-platform", "work-items", "work-queues", "work-tracking"),
            _call(
                "work_item_list",
                queue_unclaimed_only=True,
                work_queue_ids=[work_queue_id],
                exclude_terminal=True,
            ),
            _call("work_item_claim", work_item_id=claim_work_item_id),
            _call(
                "work_queue_remove_member",
                work_queue_id=work_queue_id,
                user_id=member_id,
            ),
            _text("claimed"),
        ]
    )
    state3 = _lara_state(unique_id=unique_id, user_id=system_user_id, suffix="-q3")
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            result3 = await _run_lara(di, state=state3)

    assert result3.interrupt is None
    unclaimed = _tool_json(result3.tool_results["work_item_list"])
    assert any(
        isinstance(row, dict) and row.get("work_item_id") == claim_work_item_id
        for row in unclaimed["items"]
    )
    claimed = _tool_json(result3.tool_results["work_item_claim"])
    assert claimed["work_item_id"] == claim_work_item_id
    claimed_item = await WorkItem.require_in_company("system", claim_work_item_id)
    assert isinstance(claimed_item.assignment, QueueAssignment)
    assert claimed_item.assignment.claimed_by_user_id == system_user_id
    removed = _tool_json(result3.tool_results["work_queue_remove_member"])
    assert removed["removed"] is True


@pytest.mark.asyncio
async def test_lara_worktracker_boards_and_move(
    di: FlowsDi,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    system_user_id: str,
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    _ = mock_llm_with_queue(
        [
            *_load("worktracker-platform", "work-boards", "work-items", "work-tracking"),
            _call(
                "work_board_create",
                name=f"Lara Board {unique_id}",
                board_key=f"task:lara_{unique_id}",
                columns=[
                    {
                        "board_column_id": "todo",
                        "label": "To do",
                        "item_state": "open",
                        "position": 0,
                    },
                    {
                        "board_column_id": "doing",
                        "label": "Doing",
                        "item_state": "in_progress",
                        "position": 1,
                    },
                    {
                        "board_column_id": "done",
                        "label": "Done",
                        "item_state": "done",
                        "position": 2,
                    },
                ],
            ),
            _call("work_board_list"),
            _text("board created"),
        ]
    )
    state1 = _lara_state(unique_id=unique_id, user_id=system_user_id, suffix="-b1")
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            await _seed_lara_skills(di)
            result1 = await _run_lara(di, state=state1)

    assert result1.interrupt is None
    board = _tool_json(result1.tool_results["work_board_create"])
    board_id = board["board_id"]
    assert isinstance(board_id, str) and board_id
    boards = _tool_json(result1.tool_results["work_board_list"])
    assert any(
        isinstance(row, dict) and row.get("board_id") == board_id for row in boards["items"]
    )

    _ = mock_llm_with_queue(
        [
            *_load("worktracker-platform", "work-boards", "work-items", "work-tracking"),
            _call(
                "work_item_create",
                title=f"board-move-{unique_id}",
                assignee_type="user",
                assignee_user_id=system_user_id,
                board_id=board_id,
                board_column_id="todo",
            ),
            _call("work_board_get", board_id=board_id),
            _call(
                "work_board_update",
                board_id=board_id,
                name=f"Lara Board {unique_id} upd",
            ),
            _text("item on board"),
        ]
    )
    state2 = _lara_state(unique_id=unique_id, user_id=system_user_id, suffix="-b2")
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            result2 = await _run_lara(di, state=state2)

    assert result2.interrupt is None
    created = _tool_json(result2.tool_results["work_item_create"])
    work_item_id = created["work_item_id"]
    assert isinstance(work_item_id, str)
    assert created.get("board_id") == board_id
    got = _tool_json(result2.tool_results["work_board_get"])
    assert got["board_id"] == board_id
    assert len(got["columns"]) == 3
    renamed = _tool_json(result2.tool_results["work_board_update"])
    assert renamed["name"] == f"Lara Board {unique_id} upd"

    _ = mock_llm_with_queue(
        [
            *_load("worktracker-platform", "work-boards", "work-items"),
            _call(
                "work_item_move",
                work_item_id=work_item_id,
                board_column_id="doing",
            ),
            _text("moved"),
        ]
    )
    state3 = _lara_state(unique_id=unique_id, user_id=system_user_id, suffix="-b3")
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            result3 = await _run_lara(di, state=state3)

    assert result3.interrupt is None
    moved = _tool_json(result3.tool_results["work_item_move"])
    assert moved["board_column_id"] == "doing"
    assert moved["state"] == WorkItemState.IN_PROGRESS.value
    after = await WorkItem.require_in_company("system", work_item_id)
    assert after.board_column_id == "doing"
    assert after.state == WorkItemState.IN_PROGRESS


@pytest.mark.asyncio
async def test_lara_worktracker_create_self_and_schedules(
    di: FlowsDi,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    system_user_id: str,
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    run_at = (datetime.now(UTC) + timedelta(hours=2)).replace(microsecond=0).isoformat()

    _ = mock_llm_with_queue(
        [
            *_load("worktracker-platform", "work-tracking"),
            _call(
                "work_item_create",
                title=f"self job {unique_id}",
                assignee_type="self",
            ),
            _text("self created"),
        ]
    )
    state = _lara_state(unique_id=unique_id, user_id=system_user_id, suffix="-sch")
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            await _seed_lara_skills(di)
            result = await _run_lara(di, state=state)

    assert result.interrupt is None
    created = _tool_json(result.tool_results["work_item_create"])
    work_item_id = created["work_item_id"]
    assert isinstance(work_item_id, str)
    item = await WorkItem.require_in_company("system", work_item_id)
    assert isinstance(item.assignment, UsersAssignment)
    # session_flow_id from session_id "lara:…" → flow id "lara"
    assert item.assignment.user_ids == ["flow_employee_lara"]

    _ = mock_llm_with_queue(
        [
            *_load("worktracker-platform", "work-tracking"),
            _call(
                "schedule_one_time_task",
                content_type="message",
                content=f"reminder {unique_id}",
                run_at=run_at,
                description=f"lara wt schedule {unique_id}",
            ),
            _call("list_scheduled_tasks"),
            _text("one-time scheduled"),
        ]
    )
    state_sched = _lara_state(unique_id=unique_id, user_id=system_user_id, suffix="-sch1")
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            result_sched = await _run_lara(di, state=state_sched)

    assert result_sched.interrupt is None
    schedule_task_id = _schedule_task_id_from_tool_result(
        result_sched.tool_results["schedule_one_time_task"]
    )
    listed = _tool_json(result_sched.tool_results["list_scheduled_tasks"])
    items = listed.get("items")
    assert isinstance(items, list)
    assert any(
        isinstance(item, dict)
        and item.get("schedule_task_id") == schedule_task_id
        and item.get("content") == f"reminder {unique_id}"
        for item in items
    )

    _ = mock_llm_with_queue(
        [
            *_load("worktracker-platform", "work-tracking"),
            _call("cancel_scheduled_task", schedule_task_id=schedule_task_id),
            _call(
                "schedule_cron_task",
                content_type="message",
                content=f"cron {unique_id}",
                cron="0 9 * * 1",
                description=f"lara cron {unique_id}",
            ),
            _call(
                "schedule_interval_task",
                content_type="message",
                content=f"interval {unique_id}",
                interval_minutes=60,
                description=f"lara interval {unique_id}",
            ),
            _text("schedules cancelled and created"),
        ]
    )
    state2 = _lara_state(unique_id=unique_id, user_id=system_user_id, suffix="-sch2")
    with service_client_asgi_auth_context(auth_headers_system):
        with _system_context(auth_token=auth_token_system, system_user_id=system_user_id):
            result2 = await _run_lara(di, state=state2)

    assert result2.interrupt is None
    cancelled = _tool_json(result2.tool_results["cancel_scheduled_task"])
    assert cancelled.get("cancelled") is True
    assert cancelled.get("schedule_task_id") == schedule_task_id
    cron_id = _schedule_task_id_from_tool_result(result2.tool_results["schedule_cron_task"])
    interval_id = _schedule_task_id_from_tool_result(
        result2.tool_results["schedule_interval_task"]
    )
    assert cron_id != interval_id
