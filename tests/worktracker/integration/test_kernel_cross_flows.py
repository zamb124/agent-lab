"""
Строгие интеграционные тесты ядра задач WorkItem.

Без моков и monkeypatch: реальный Postgres (platform_worktracker), реальный Redis
(publish events / notify_user), реальный CRM-репозиторий (platform_crm) и реальный
flows-контейнер для HITL. Покрываются happy- и unhappy-сценарии и соседи HITL/CRM.

Уровни (testing_invariants.mdc): сервис из контейнера (`container.work_item_service`,
`container.hitl_work_item_service`) и репозиторий-сосед CRM. Изоляция — `unique_id`.
"""

from __future__ import annotations

import uuid

import pytest

from apps.crm.container import get_crm_container
from apps.crm.db.models import CRMEntity
from apps.flows.src.models.hitl_schemas import HitlHandoffCommand
from apps.flows.tools.work_item_tools import (
    work_item_complete,
    work_item_create,
    work_item_list,
)
from core.files.file_ref import FileRef
from core.state import ExecutionState
from core.state.interrupt import HandoffMode
from core.variables.models import normalize_variables_map
from core.worktracker.models import (
    AgentAssignment,
    BoardColumn,
    CrmEntityLink,
    QueueAssignment,
    SystemActor,
    UnassignedAssignment,
    UserActor,
    UsersAssignment,
    WorkItemCommentRole,
    WorkItemHook,
    WorkItemHookEvent,
    WorkItemKind,
    WorkItemResolution,
    WorkItemState,
)
from core.worktracker.service import WorkItemService

pytestmark = pytest.mark.asyncio


# ============================ Ядро: создание ============================


async def test_create_work_item_persists_defaults(app, container, unique_id):
    svc = container.work_item_service
    item = await svc.create(
        company_id="system",
        title=f"task-{unique_id}",
        created_by=SystemActor(),
    )
    assert item.state is WorkItemState.OPEN
    assert item.kind is WorkItemKind.GENERIC
    assert item.blocking is False
    assert isinstance(item.assignment, UnassignedAssignment)

    fetched = await svc.get("system", item.work_item_id)
    assert fetched.work_item_id == item.work_item_id
    assert fetched.title == f"task-{unique_id}"


async def test_create_manual_task_assigns_creator_and_generic_board(app, container, unique_id):
    svc = container.work_item_service
    user_id = f"user_{unique_id}"
    item = await svc.create_manual_task(
        company_id="system",
        title=f"manual-{unique_id}",
        created_by=UserActor(user_id=user_id),
    )
    assert isinstance(item.assignment, UsersAssignment)
    assert item.assignment.user_ids == [user_id]
    assert item.board_id is not None
    assert item.board_column_id == "todo"

    boards = await svc.list_boards("system")
    assert len(boards) == 1
    assert boards[0].board_key == "generic"


async def test_get_unknown_work_item_raises(app, container, unique_id):
    with pytest.raises(ValueError):
        await container.work_item_service.get("system", f"wi_missing_{unique_id}")


# ============================ Ядро: доска и переходы ============================


async def _board_with_three_columns(container, unique_id):
    return await container.work_item_service.create_board(
        company_id="system",
        name=f"board-{unique_id}",
        columns=[
            BoardColumn(board_column_id="todo", label="To do", state=WorkItemState.OPEN, position=0),
            BoardColumn(
                board_column_id="doing", label="Doing", state=WorkItemState.IN_PROGRESS, position=1
            ),
            BoardColumn(board_column_id="done", label="Done", state=WorkItemState.DONE, position=2),
        ],
    )


async def test_create_on_board_uses_first_column_state(app, container, unique_id):
    board = await _board_with_three_columns(container, unique_id)
    item = await container.work_item_service.create(
        company_id="system",
        title=f"board-task-{unique_id}",
        created_by=SystemActor(),
        board_id=board.board_id,
    )
    assert item.board_column_id == "todo"
    assert item.state is WorkItemState.OPEN


async def test_move_between_columns_changes_state(app, container, unique_id):
    board = await _board_with_three_columns(container, unique_id)
    svc = container.work_item_service
    item = await svc.create(
        company_id="system",
        title=f"mv-{unique_id}",
        created_by=SystemActor(),
        board_id=board.board_id,
        board_column_id="todo",
    )
    moved = await svc.move(
        company_id="system", work_item_id=item.work_item_id, board_column_id="doing"
    )
    assert moved.board_column_id == "doing"
    assert moved.state is WorkItemState.IN_PROGRESS


async def test_move_to_unknown_column_raises(app, container, unique_id):
    board = await _board_with_three_columns(container, unique_id)
    svc = container.work_item_service
    item = await svc.create(
        company_id="system",
        title=f"badmv-{unique_id}",
        created_by=SystemActor(),
        board_id=board.board_id,
        board_column_id="todo",
    )
    with pytest.raises(ValueError):
        await svc.move(
            company_id="system", work_item_id=item.work_item_id, board_column_id="missing"
        )


async def test_move_from_terminal_state_raises(app, container, unique_id):
    svc = container.work_item_service
    item = await svc.create(
        company_id="system", title=f"term-{unique_id}", created_by=SystemActor()
    )
    completion = await svc.complete(company_id="system", work_item_id=item.work_item_id)
    assert completion.newly_terminal is True
    assert completion.work_item.state is WorkItemState.DONE
    with pytest.raises(ValueError):
        await svc.move(
            company_id="system", work_item_id=item.work_item_id, state=WorkItemState.IN_PROGRESS
        )


# ============================ Ядро: завершение (идемпотентность) ============================


async def test_complete_is_idempotent(app, container, unique_id):
    svc = container.work_item_service
    item = await svc.create(
        company_id="system", title=f"done-{unique_id}", created_by=SystemActor()
    )
    first = await svc.complete(
        company_id="system",
        work_item_id=item.work_item_id,
        resolution=WorkItemResolution(text="ok"),
    )
    assert first.newly_terminal is True
    assert first.work_item.resolution is not None
    assert first.work_item.resolution.text == "ok"

    second = await svc.complete(company_id="system", work_item_id=item.work_item_id)
    assert second.newly_terminal is False
    assert second.work_item.state is WorkItemState.DONE


# ============================ Ядро: очереди и claim ============================


async def test_create_queue_duplicate_slug_raises(app, container, unique_id):
    slug = f"q-{unique_id}"
    svc = container.work_item_service
    await svc.create_queue(company_id="system", name="Q", slug=slug)
    with pytest.raises(ValueError):
        await svc.create_queue(company_id="system", name="Q2", slug=slug)


async def test_claim_non_queue_item_raises(app, container, unique_id):
    svc = container.work_item_service
    item = await svc.create(
        company_id="system", title=f"noq-{unique_id}", created_by=SystemActor()
    )
    with pytest.raises(ValueError):
        await svc.claim(company_id="system", work_item_id=item.work_item_id, user_id="u1")


async def test_claim_by_non_member_then_member(app, container, unique_id):
    svc = container.work_item_service
    queue = await svc.create_queue(company_id="system", name="Ops", slug=f"ops-{unique_id}")
    item = await svc.create(
        company_id="system",
        title=f"claim-{unique_id}",
        created_by=SystemActor(),
        assignment=QueueAssignment(work_queue_id=queue.work_queue_id),
    )
    outsider = f"user_out_{unique_id}"
    with pytest.raises(PermissionError):
        await svc.claim(company_id="system", work_item_id=item.work_item_id, user_id=outsider)

    member = f"user_in_{unique_id}"
    await svc.add_queue_member(
        company_id="system",
        work_queue_id=queue.work_queue_id,
        member=UserActor(user_id=member),
    )
    claimed = await svc.claim(
        company_id="system", work_item_id=item.work_item_id, user_id=member
    )
    assert isinstance(claimed.assignment, QueueAssignment)
    assert claimed.assignment.claimed_by_user_id == member
    assert claimed.state is WorkItemState.IN_PROGRESS


# ============================ Ядро: фильтрация списка ============================


async def test_list_filters_by_state_and_kind(app, container, unique_id):
    svc = container.work_item_service
    ns = f"ns-{unique_id}"
    a = await svc.create(
        company_id="system", title=f"a-{unique_id}", created_by=SystemActor(), namespace=ns
    )
    b = await svc.create(
        company_id="system", title=f"b-{unique_id}", created_by=SystemActor(), namespace=ns
    )
    await svc.complete(company_id="system", work_item_id=b.work_item_id)

    open_items = await svc.list("system", namespace=ns, state=WorkItemState.OPEN)
    done_items = await svc.list("system", namespace=ns, state=WorkItemState.DONE)
    open_ids = {i.work_item_id for i in open_items}
    done_ids = {i.work_item_id for i in done_items}
    assert a.work_item_id in open_ids
    assert b.work_item_id in done_ids
    assert b.work_item_id not in open_ids


# ============================ Сосед HITL (flows) ============================


def _hitl_command(unique_id: str) -> HitlHandoffCommand:
    key = f"hitl:test:{unique_id}"
    return HitlHandoffCommand(
        correlation_id=uuid.uuid5(uuid.NAMESPACE_URL, key),
        idempotency_key=key,
        execution_branch_id=f"branch-{unique_id}",
        node_schedule_sequence=1,
        node_id="h",
        tool_call_id=None,
    )


def _hitl_state(unique_id: str) -> ExecutionState:
    flow_id = f"hitl_flow_{unique_id}"
    ctx = f"ctx-{unique_id}"
    return ExecutionState(
        task_id=f"a2a-{unique_id}",
        context_id=ctx,
        user_id="test_user",
        session_id=f"{flow_id}:{ctx}",
        branch_id="default",
    )


async def test_hitl_register_creates_operator_handoff_work_item(app, container, unique_id):
    slug = f"hitl-{unique_id}"
    await container.work_item_service.create_queue(
        company_id="system", name="HITL", slug=slug
    )
    state = _hitl_state(unique_id)
    command = _hitl_command(unique_id)

    cid, work_item_id = await container.hitl_work_item_service.register_handoff(
        state,
        question="Нужна помощь оператора",
        task_title="Support",
        assignee_queue_slug=slug,
        handoff_mode=HandoffMode.SINGLE_REPLY,
        command=command,
    )
    assert str(cid) == str(command.correlation_id)

    item = await container.work_item_service.get("system", work_item_id)
    assert item.kind is WorkItemKind.OPERATOR_HANDOFF
    assert item.blocking is True
    assert isinstance(item.assignment, QueueAssignment)
    completed_hooks = item.hooks_for(WorkItemHookEvent.COMPLETED)
    assert len(completed_hooks) == 1
    completed_hook = completed_hooks[0]
    assert completed_hook.service == "flows"
    assert completed_hook.path == "/flows/api/v1/internal/work-items/completed"
    assert completed_hook.binding["correlation_id"] == str(cid)
    assert completed_hook.binding["session_id"] == state.session_id
    # comment-хук для takeover-стрима
    assert len(item.hooks_for(WorkItemHookEvent.COMMENT)) == 1
    # flow_session link на исходную сессию
    assert any(getattr(link, "session_id", None) == state.session_id for link in item.links)


async def test_hitl_register_is_idempotent_by_correlation(app, container, unique_id):
    slug = f"hitl2-{unique_id}"
    await container.work_item_service.create_queue(company_id="system", name="H", slug=slug)
    state = _hitl_state(unique_id)
    command = _hitl_command(unique_id)

    cid1, id1 = await container.hitl_work_item_service.register_handoff(
        state, question="q", task_title="t", assignee_queue_slug=slug,
        handoff_mode=HandoffMode.SINGLE_REPLY, command=command,
    )
    cid2, id2 = await container.hitl_work_item_service.register_handoff(
        state, question="q", task_title="t", assignee_queue_slug=slug,
        handoff_mode=HandoffMode.SINGLE_REPLY, command=command,
    )
    assert id1 == id2
    assert str(cid1) == str(cid2)


async def test_hitl_register_unknown_queue_raises(app, container, unique_id):
    state = _hitl_state(unique_id)
    command = _hitl_command(unique_id)
    with pytest.raises(ValueError):
        await container.hitl_work_item_service.register_handoff(
            state,
            question="q",
            task_title="t",
            assignee_queue_slug=f"no-such-queue-{unique_id}",
            handoff_mode=HandoffMode.SINGLE_REPLY,
            command=command,
        )


async def test_hitl_resume_with_invalid_binding_raises(app, container, unique_id):
    # binding без context_data_snapshot.channel — resume невозможен
    binding = {
        "session_id": f"flow_{unique_id}:ctx",
        "flow_id": f"flow_{unique_id}",
        "branch_id": "default",
        "end_user_id": "test_user",
        "context_data_snapshot": {},
    }
    with pytest.raises(ValueError):
        await container.hitl_work_item_service.resume_from_completion(
            company_id="system",
            work_item_id=f"wi_missing_{unique_id}",
            binding=binding,
            resolution=WorkItemResolution(text="done"),
        )


# ============================ Агентские тулы (fire-and-forget / self) ============================


async def test_agent_tool_creates_self_assigned_job(app, container, unique_id):
    flow_id = f"agent_{unique_id}"
    state = ExecutionState(
        task_id=f"t-{unique_id}",
        context_id=f"c-{unique_id}",
        user_id="test_user",
        session_id=f"{flow_id}:c-{unique_id}",
    )
    created = await work_item_create.run(
        {
            "title": f"job-{unique_id}",
            "description": "self job",
            "assignee_type": "self",
            "priority": "high",
            "blocking": False,
        },
        state,
    )
    work_item_id = created["work_item_id"]
    item = await container.work_item_service.get("system", work_item_id)
    assert item.kind is WorkItemKind.AGENT_JOB
    assert item.blocking is False
    assert isinstance(item.assignment, AgentAssignment)
    assert item.assignment.flow_id == flow_id

    listed = await work_item_list.run({"state_filter": "open"}, state)
    assert any(row["work_item_id"] == work_item_id for row in listed["items"])

    done = await work_item_complete.run(
        {"work_item_id": work_item_id, "resolution_text": "finished"}, state
    )
    assert done["state"] == WorkItemState.DONE.value


async def test_agent_tool_queue_assignment_requires_existing_queue(app, container, unique_id):
    flow_id = f"agent2_{unique_id}"
    state = ExecutionState(
        task_id=f"t2-{unique_id}",
        context_id=f"c2-{unique_id}",
        user_id="test_user",
        session_id=f"{flow_id}:c2-{unique_id}",
    )
    with pytest.raises(ValueError):
        await work_item_create.run(
            {
                "title": f"q-job-{unique_id}",
                "assignee_type": "queue",
                "assignee_queue_slug": f"absent-{unique_id}",
            },
            state,
        )


# ============================ Сосед CRM (Networkle) ============================


async def _create_crm_task_entity(unique_id: str) -> CRMEntity:
    crm = get_crm_container()
    entity = CRMEntity(
        entity_id=f"ent_{unique_id}",
        company_id="system",
        namespace=f"crm-ns-{unique_id}",
        entity_type="task",
        name=f"CRM task {unique_id}",
        user_id="test_user",
        attributes={},
    )
    return await crm.entity_repository.create(entity)


async def test_crm_task_pairs_with_work_item_and_kernel_owns_state(app, container, unique_id):
    crm_entity = await _create_crm_task_entity(unique_id)
    svc = container.work_item_service
    work_item = await svc.create(
        company_id="system",
        title=crm_entity.name,
        created_by=SystemActor(),
        kind=WorkItemKind.CRM_ACTIVITY,
        namespace=crm_entity.namespace,
        links=[CrmEntityLink(entity_id=crm_entity.entity_id)],
    )
    # 1:1 связь ссылается на реальную CRM-сущность
    crm_links = [link for link in work_item.links if isinstance(link, CrmEntityLink)]
    assert len(crm_links) == 1
    assert crm_links[0].entity_id == crm_entity.entity_id

    # work-состояние живёт в ядре: перенос/завершение меняют WorkItem
    completion = await svc.complete(
        company_id="system", work_item_id=work_item.work_item_id
    )
    assert completion.work_item.state is WorkItemState.DONE

    # CRM-сущность остаётся графовым узлом, её статус (entity.status) не затронут
    crm = get_crm_container()
    refreshed = await crm.entity_repository.get(crm_entity.entity_id)
    assert refreshed is not None
    assert refreshed.entity_type == "task"
    assert refreshed.status == "active"


async def test_crm_task_work_item_visible_in_namespace_list(app, container, unique_id):
    crm_entity = await _create_crm_task_entity(unique_id)
    svc = container.work_item_service
    work_item = await svc.create(
        company_id="system",
        title=crm_entity.name,
        created_by=SystemActor(),
        kind=WorkItemKind.CRM_ACTIVITY,
        namespace=crm_entity.namespace,
        assignment=UsersAssignment(user_ids=["test_user"]),
        links=[CrmEntityLink(entity_id=crm_entity.entity_id)],
    )
    items = await svc.list("system", namespace=crm_entity.namespace, kind=WorkItemKind.CRM_ACTIVITY)
    assert any(i.work_item_id == work_item.work_item_id for i in items)


# ============================ Гибкое переназначение (reassign) ============================


async def test_reassign_between_user_agent_queue(app, container, unique_id):
    """Любая задача переназначается на человека/агента/очередь в любой момент."""
    svc = container.work_item_service
    queue = await svc.create_queue(company_id="system", name="Q", slug=f"reassign-{unique_id}")
    item = await svc.create(
        company_id="system", title=f"flex-{unique_id}", created_by=SystemActor()
    )
    assert isinstance(item.assignment, UnassignedAssignment)

    to_user = await svc.reassign(
        company_id="system",
        work_item_id=item.work_item_id,
        assignment=UsersAssignment(user_ids=["u1"]),
    )
    assert isinstance(to_user.assignment, UsersAssignment)

    to_agent = await svc.reassign(
        company_id="system",
        work_item_id=item.work_item_id,
        assignment=AgentAssignment(flow_id=f"flow_{unique_id}"),
    )
    assert isinstance(to_agent.assignment, AgentAssignment)

    to_queue = await svc.reassign(
        company_id="system",
        work_item_id=item.work_item_id,
        assignment=QueueAssignment(work_queue_id=queue.work_queue_id),
    )
    assert isinstance(to_queue.assignment, QueueAssignment)


async def test_reassign_terminal_raises(app, container, unique_id):
    svc = container.work_item_service
    item = await svc.create(
        company_id="system", title=f"term-reassign-{unique_id}", created_by=SystemActor()
    )
    _ = await svc.complete(company_id="system", work_item_id=item.work_item_id)
    with pytest.raises(ValueError):
        await svc.reassign(
            company_id="system",
            work_item_id=item.work_item_id,
            assignment=AgentAssignment(flow_id="f"),
        )


async def test_cancel_and_reject_terminal_states(app, container, unique_id):
    svc = container.work_item_service
    to_cancel = await svc.create(
        company_id="system", title=f"cancel-{unique_id}", created_by=SystemActor()
    )
    cancelled = await svc.cancel(company_id="system", work_item_id=to_cancel.work_item_id)
    assert cancelled.work_item.state is WorkItemState.CANCELLED

    to_reject = await svc.create(
        company_id="system", title=f"reject-{unique_id}", created_by=SystemActor()
    )
    rejected = await svc.reject(
        company_id="system", work_item_id=to_reject.work_item_id, reason="bad"
    )
    assert rejected.work_item.state is WorkItemState.FAILED


# ============================ Единый механизм хуков ============================


class _RecordingHookDispatcher:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def dispatch(self, work_item, hook, payload):  # noqa: ANN001
        _ = (work_item, payload)
        self.events.append(hook.event.value)


async def test_hooks_dispatched_on_assigned_comment_completed(app, container, unique_id):
    recorder = _RecordingHookDispatcher()
    svc = WorkItemService(
        repository=container.worktracker_repository, hook_dispatcher=recorder
    )
    hooks = [
        WorkItemHook(event=WorkItemHookEvent.ASSIGNED, service="flows", path="/x"),
        WorkItemHook(event=WorkItemHookEvent.COMMENT, service="flows", path="/y"),
        WorkItemHook(event=WorkItemHookEvent.COMPLETED, service="flows", path="/z"),
    ]
    item = await svc.create(
        company_id="system",
        title=f"hooks-{unique_id}",
        created_by=SystemActor(),
        kind=WorkItemKind.AGENT_JOB,
        assignment=AgentAssignment(flow_id=f"flow_{unique_id}"),
        hooks=hooks,
    )
    # create с AgentAssignment → assigned-хук
    assert "assigned" in recorder.events

    await svc.add_comment(
        company_id="system",
        work_item_id=item.work_item_id,
        author=UserActor(user_id="op1"),
        role=WorkItemCommentRole.OPERATOR,
        text="hi",
    )
    assert "comment" in recorder.events

    _ = await svc.complete(company_id="system", work_item_id=item.work_item_id)
    assert "completed" in recorder.events


async def test_work_item_attachments_variables_comment_files_roundtrip(app, container, unique_id):
    svc = container.work_item_service
    file_ref = FileRef(
        file_id=f"file_{unique_id}",
        original_name="spec.pdf",
        content_type="application/pdf",
        file_size=42,
    )
    variables = normalize_variables_map({"customer": "ACME", "tier": {"value": "gold", "secret": False}})
    item = await svc.create(
        company_id="system",
        title=f"files-{unique_id}",
        created_by=SystemActor(),
        variables=variables,
        attachments=[file_ref],
    )
    assert item.attachments[0].file_id == file_ref.file_id
    assert item.variables["customer"].value == "ACME"

    comment = await svc.add_comment(
        company_id="system",
        work_item_id=item.work_item_id,
        author=SystemActor(),
        role=WorkItemCommentRole.SYSTEM,
        text="attached",
        files=[file_ref],
    )
    assert comment.files[0].original_name == "spec.pdf"

    completion = await svc.complete(
        company_id="system",
        work_item_id=item.work_item_id,
        resolution=WorkItemResolution(text="done", files=[file_ref]),
    )
    assert completion.work_item.resolution is not None
    assert completion.work_item.resolution.files[0].file_id == file_ref.file_id

    fetched = await svc.get("system", item.work_item_id)
    assert fetched.attachments[0].file_id == file_ref.file_id
    assert fetched.variables["tier"].value == "gold"


async def test_reassign_to_agent_dispatches_assigned_hook(app, container, unique_id):
    recorder = _RecordingHookDispatcher()
    svc = WorkItemService(
        repository=container.worktracker_repository, hook_dispatcher=recorder
    )
    item = await svc.create(
        company_id="system",
        title=f"reassign-hook-{unique_id}",
        created_by=SystemActor(),
        hooks=[WorkItemHook(event=WorkItemHookEvent.ASSIGNED, service="flows", path="/x")],
    )
    recorder.events.clear()
    await svc.reassign(
        company_id="system",
        work_item_id=item.work_item_id,
        assignment=AgentAssignment(flow_id=f"flow_{unique_id}"),
    )
    assert recorder.events == ["assigned"]
