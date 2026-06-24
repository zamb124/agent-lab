"""Юнит-тесты доменных моделей ядра задач WorkItem (без БД)."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import TypeAdapter

from core.worktracker.models import (
    TERMINAL_WORK_ITEM_STATES,
    AgentActor,
    AgentAssignment,
    CrmEntityLink,
    FlowSessionLink,
    QueueAssignment,
    SystemActor,
    UnassignedAssignment,
    UserActor,
    UsersAssignment,
    WorkActor,
    WorkItem,
    WorkItemAssignment,
    WorkItemKind,
    WorkItemLink,
    WorkItemPriority,
    WorkItemState,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_terminal_states_exact() -> None:
    assert TERMINAL_WORK_ITEM_STATES == frozenset(
        {WorkItemState.DONE, WorkItemState.CANCELLED, WorkItemState.FAILED}
    )
    assert WorkItemState.OPEN not in TERMINAL_WORK_ITEM_STATES
    assert WorkItemState.BLOCKED not in TERMINAL_WORK_ITEM_STATES


def test_actor_discriminated_union_roundtrip() -> None:
    adapter: TypeAdapter[WorkActor] = TypeAdapter(WorkActor)
    for actor in (
        UserActor(user_id="user_1"),
        AgentActor(flow_id="flow_1", session_id="flow_1:ctx"),
        SystemActor(),
    ):
        restored = adapter.validate_python(actor.model_dump(mode="json"))
        assert type(restored) is type(actor)


def test_assignment_discriminated_union_roundtrip() -> None:
    adapter: TypeAdapter[WorkItemAssignment] = TypeAdapter(WorkItemAssignment)
    cases: list[WorkItemAssignment] = [
        UnassignedAssignment(),
        UsersAssignment(user_ids=["user_1", "user_2"]),
        QueueAssignment(work_queue_id="wq_1", claimed_by_user_id="user_9"),
        AgentAssignment(flow_id="flow_1", branch_id="main"),
    ]
    for assignment in cases:
        restored = adapter.validate_python(assignment.model_dump(mode="json"))
        assert type(restored) is type(assignment)


def test_link_discriminated_union_roundtrip() -> None:
    adapter: TypeAdapter[WorkItemLink] = TypeAdapter(WorkItemLink)
    links: list[WorkItemLink] = [
        CrmEntityLink(entity_id="ent_1"),
        FlowSessionLink(session_id="flow_1:ctx", a2a_task_id="t1", context_id="ctx"),
    ]
    for link in links:
        restored = adapter.validate_python(link.model_dump(mode="json"))
        assert type(restored) is type(link)


def test_work_item_defaults() -> None:
    item = WorkItem(
        work_item_id="wi_1",
        company_id="company_1",
        title="Сделать",
        created_by=SystemActor(),
        created_at=_now(),
        updated_at=_now(),
    )
    assert item.kind is WorkItemKind.GENERIC
    assert item.state is WorkItemState.OPEN
    assert item.priority is WorkItemPriority.NORMAL
    assert item.blocking is False
    assert isinstance(item.assignment, UnassignedAssignment)
    assert item.hooks == []
