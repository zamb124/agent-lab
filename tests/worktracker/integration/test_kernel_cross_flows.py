"""
Строгие интеграционные тесты ядра задач WorkItem.

Без моков и monkeypatch: реальный Postgres (platform_worktracker), реальный Redis
(publish events / notify_user), реальный CRM-репозиторий (platform_crm) и реальный
FlowsDi для HITL. Покрываются happy- и unhappy-сценарии и соседи HITL/CRM.

Уровни (testing.mdc): сервис из DI (`di.work_item_service`,
`di.node_constructor.hitl_work_item_service`) и репозиторий-сосед CRM. Изоляция — `unique_id`.
"""

from __future__ import annotations

import uuid

import pytest

from apps.crm.models.crm_entity import CRMEntity
from apps.flows.src.models.hitl_conversation import ConversationTurnRole
from apps.flows.src.models.hitl_schemas import HitlHandoffCommand
from apps.flows.src.runtime.a2a_messages import build_user_message
from apps.flows.src.state import ExecutionState
from apps.flows.src.state.interrupt import HandoffMode
from apps.flows.tools.worktracker.work_item_tools import (
    work_item_complete,
    work_item_create,
    work_item_list,
)
from core.files.file_ref import FileRef
from core.identity.flow_employee import flow_employee_user_id
from core.variables.models import normalize_variables_map
from core.worktracker.access_service import WorkQueueAccessService
from core.worktracker.models import (
    TERMINAL_WORK_ITEM_STATES,
    BoardColumn,
    CrmEntityLink,
    QueueAssignment,
    SystemActor,
    UnassignedAssignment,
    UserActor,
    UsersAssignment,
    WorkItem,
    WorkItemCommentRole,
    WorkItemHook,
    WorkItemHookEvent,
    WorkItemInteractionMode,
    WorkItemKind,
    WorkItemResolution,
    WorkItemState,
)
from core.worktracker.service import WorkItemService
from tests.fixtures.flow_employee_test_helpers import (
    cleanup_flow_employee_for_tests,
    provision_flow_employee_for_tests,
)

pytestmark = pytest.mark.asyncio


# ============================ Ядро: создание ============================


async def test_create_work_item_persists_defaults(app, di, unique_id):
    svc = di.work_item_service
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


async def test_create_manual_task_assigns_creator_and_generic_board(app, di, unique_id):
    svc = di.work_item_service
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
    generic = [b for b in boards if b.board_key == "generic"]
    assert len(generic) >= 1
    assert item.board_id in {b.board_id for b in generic}


async def test_get_unknown_work_item_raises(app, di, unique_id):
    with pytest.raises(ValueError):
        await WorkItem.require_in_company("system", f"wi_missing_{unique_id}")


# ============================ Ядро: доска и переходы ============================


async def _board_with_three_columns(di, unique_id):
    return await di.work_item_service.create_board(
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


async def test_create_on_board_uses_first_column_state(app, di, unique_id):
    board = await _board_with_three_columns(di, unique_id)
    item = await di.work_item_service.create(
        company_id="system",
        title=f"board-task-{unique_id}",
        created_by=SystemActor(),
        board_id=board.board_id,
    )
    assert item.board_column_id == "todo"
    assert item.state is WorkItemState.OPEN


async def test_move_between_columns_changes_state(app, di, unique_id):
    board = await _board_with_three_columns(di, unique_id)
    svc = di.work_item_service
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


async def test_move_to_unknown_column_raises(app, di, unique_id):
    board = await _board_with_three_columns(di, unique_id)
    svc = di.work_item_service
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


async def test_move_from_terminal_state_raises(app, di, unique_id):
    svc = di.work_item_service
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


async def test_complete_is_idempotent(app, di, unique_id):
    svc = di.work_item_service
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


async def test_create_queue_duplicate_slug_raises(app, di, unique_id):
    slug = f"q-{unique_id}"
    svc = di.work_item_service
    await svc.create_queue(company_id="system", name="Q", slug=slug)
    with pytest.raises(ValueError):
        await svc.create_queue(company_id="system", name="Q2", slug=slug)


async def test_claim_non_queue_item_raises(app, di, unique_id):
    svc = di.work_item_service
    item = await svc.create(
        company_id="system", title=f"noq-{unique_id}", created_by=SystemActor()
    )
    with pytest.raises(ValueError):
        await svc.claim(company_id="system", work_item_id=item.work_item_id, user_id="u1")


async def test_claim_by_non_member_then_member(app, di, unique_id):
    svc = di.work_item_service
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


async def test_list_filters_by_state_and_kind(app, di, unique_id):
    svc = di.work_item_service
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


async def test_hitl_register_creates_operator_handoff_work_item(app, di, unique_id):
    slug = f"hitl-{unique_id}"
    await di.work_item_service.create_queue(
        company_id="system", name="HITL", slug=slug
    )
    state = _hitl_state(unique_id)
    command = _hitl_command(unique_id)

    cid, work_item_id = await di.node_constructor.hitl_work_item_service.register_handoff(
        state,
        question="Нужна помощь оператора",
        task_title="Support",
        assignee_queue_slug=slug,
        handoff_mode=HandoffMode.SINGLE_REPLY,
        command=command,
    )
    assert str(cid) == str(command.correlation_id)

    item = await WorkItem.require_in_company("system", work_item_id)
    assert item.kind is WorkItemKind.OPERATOR_HANDOFF
    assert item.blocking is True
    assert isinstance(item.assignment, QueueAssignment)
    completed_hooks = item.hooks_for(WorkItemHookEvent.COMPLETED)
    assert len(completed_hooks) == 1
    completed_hook = completed_hooks[0]
    assert completed_hook.service == "flows"
    assert completed_hook.path == "platform:events"
    assert completed_hook.binding["correlation_id"] == str(cid)
    assert completed_hook.binding["session_id"] == state.session_id
    # HITL больше не регистрирует comment-хук: диалог идёт durable append в лог сессии
    assert item.hooks_for(WorkItemHookEvent.COMMENT) == []
    # HITL: Submit оператора = complete + closing reply; чат не read-only
    assert item.interaction is not None
    assert item.interaction.mode is WorkItemInteractionMode.SINGLE_REPLY
    # flow_session link на исходную сессию с flow_id/branch_id для встроенного чата
    link = item.flow_session_link()
    assert link is not None
    assert link.session_id == state.session_id
    assert link.flow_id == state.session_flow_id
    assert link.branch_id == state.branch_id


async def test_hitl_single_reply_complete_requires_resolution(app, di, unique_id):
    slug = f"hitl-sr-{unique_id}"
    await di.work_item_service.create_queue(
        company_id="system", name="HITL", slug=slug
    )
    state = _hitl_state(unique_id)
    command = _hitl_command(unique_id)
    _cid, work_item_id = await di.node_constructor.hitl_work_item_service.register_handoff(
        state,
        question="q",
        task_title="t",
        assignee_queue_slug=slug,
        handoff_mode=HandoffMode.SINGLE_REPLY,
        command=command,
    )
    with pytest.raises(ValueError, match="single_reply"):
        await di.work_item_service.complete(
            company_id="system",
            work_item_id=work_item_id,
            resolution=WorkItemResolution(text=""),
        )
    completed = await di.work_item_service.complete(
        company_id="system",
        work_item_id=work_item_id,
        resolution=WorkItemResolution(text="ответ оператора"),
    )
    assert completed.work_item.state is WorkItemState.DONE


async def test_hitl_register_is_idempotent_by_correlation(app, di, unique_id):
    slug = f"hitl2-{unique_id}"
    await di.work_item_service.create_queue(company_id="system", name="H", slug=slug)
    state = _hitl_state(unique_id)
    command = _hitl_command(unique_id)

    cid1, id1 = await di.node_constructor.hitl_work_item_service.register_handoff(
        state, question="q", task_title="t", assignee_queue_slug=slug,
        handoff_mode=HandoffMode.SINGLE_REPLY, command=command,
    )
    cid2, id2 = await di.node_constructor.hitl_work_item_service.register_handoff(
        state, question="q", task_title="t", assignee_queue_slug=slug,
        handoff_mode=HandoffMode.SINGLE_REPLY, command=command,
    )
    assert id1 == id2
    assert str(cid1) == str(cid2)


async def test_hitl_register_unknown_queue_raises(app, di, unique_id):
    state = _hitl_state(unique_id)
    command = _hitl_command(unique_id)
    with pytest.raises(ValueError):
        await di.node_constructor.hitl_work_item_service.register_handoff(
            state,
            question="q",
            task_title="t",
            assignee_queue_slug=f"no-such-queue-{unique_id}",
            handoff_mode=HandoffMode.SINGLE_REPLY,
            command=command,
        )


async def test_hitl_resume_with_invalid_binding_raises(app, di, unique_id):
    # binding без context_data_snapshot.channel — resume невозможен
    binding = {
        "session_id": f"flow_{unique_id}:ctx",
        "flow_id": f"flow_{unique_id}",
        "branch_id": "default",
        "end_user_id": "test_user",
        "context_data_snapshot": {},
    }
    with pytest.raises(ValueError):
        await di.node_constructor.hitl_work_item_service.resume_from_completion(
            work_item_id=f"wi_missing_{unique_id}",
            binding=binding,
            resolution=WorkItemResolution(text="done"),
        )


# ============================ HITL: встроенный чат карточки (тот же лог сессии) ============================


async def test_hitl_operator_chat_shares_session_log_and_appends(app, di, unique_id):
    """Оператор видит тот же лог сессии; takeover-ответ durable-append'ится и идемпотентен."""
    slug = f"hitlchat-{unique_id}"
    queue = await di.work_item_service.create_queue(
        company_id="system", name="HITLChat", slug=slug
    )
    member = f"op_{unique_id}"
    await di.work_item_service.add_queue_member(
        company_id="system",
        work_queue_id=queue.work_queue_id,
        member=UserActor(user_id=member),
    )

    state = _hitl_state(unique_id)
    user_msg = build_user_message(
        "Привет, нужна помощь",
        "start_node",
        context_id=state.context_id,
        task_id=state.task_id,
    )
    state.messages.append(user_msg)
    await di.workflow_runtime.save_state(state.session_id, state)

    command = _hitl_command(unique_id)
    _cid, work_item_id = await di.node_constructor.hitl_work_item_service.register_handoff(
        state,
        question="q",
        task_title="t",
        assignee_queue_slug=slug,
        handoff_mode=HandoffMode.TAKEOVER,
        command=command,
    )
    await di.work_item_service.claim(
        company_id="system", work_item_id=work_item_id, user_id=member
    )

    conv = di.hitl_conversation_service
    snapshot = await conv.get_snapshot(
        company_id="system", work_item_id=work_item_id, operator_user_id=member
    )
    assert snapshot.policy.mode is WorkItemInteractionMode.TAKEOVER
    assert snapshot.policy.can_send is True
    assert snapshot.policy.can_complete is True
    assert any(turn.role == ConversationTurnRole.USER for turn in snapshot.turns)

    turn = await conv.append_operator_message(
        company_id="system",
        work_item_id=work_item_id,
        operator_user_id=member,
        text="Здравствуйте! Помогаю.",
        idempotency_key="k1",
    )
    assert turn.role == ConversationTurnRole.OPERATOR

    repeat = await conv.append_operator_message(
        company_id="system",
        work_item_id=work_item_id,
        operator_user_id=member,
        text="Здравствуйте! Помогаю.",
        idempotency_key="k1",
    )
    assert repeat.message_id == turn.message_id

    after = await conv.get_snapshot(
        company_id="system", work_item_id=work_item_id, operator_user_id=member
    )
    operator_turns = [t for t in after.turns if t.role == ConversationTurnRole.OPERATOR]
    assert len(operator_turns) == 1
    assert operator_turns[0].text == "Здравствуйте! Помогаю."


async def test_hitl_operator_chat_materializes_state_content_without_messages(
    app, di, unique_id
):
    """Code-only путь: state.content без messages → оператор видит реплику пользователя."""
    slug = f"hitlchat3-{unique_id}"
    queue = await di.work_item_service.create_queue(
        company_id="system", name="HITLChat3", slug=slug
    )
    member = f"op_{unique_id}"
    await di.work_item_service.add_queue_member(
        company_id="system",
        work_queue_id=queue.work_queue_id,
        member=UserActor(user_id=member),
    )

    state = _hitl_state(unique_id)
    user_text = "Нужен перехват диалога по спорному возврату"
    state.content = user_text
    await di.workflow_runtime.save_state(state.session_id, state)

    command = _hitl_command(unique_id)
    _cid, work_item_id = await di.node_constructor.hitl_work_item_service.register_handoff(
        state,
        question="q",
        task_title="t",
        assignee_queue_slug=slug,
        handoff_mode=HandoffMode.TAKEOVER,
        command=command,
    )
    await di.hitl_conversation_service.materialize_triggering_user_content(
        company_id="system",
        work_item_id=work_item_id,
        state=state,
        node_id="hitl_takeover_demo",
    )
    await di.work_item_service.claim(
        company_id="system", work_item_id=work_item_id, user_id=member
    )

    snapshot = await di.hitl_conversation_service.get_snapshot(
        company_id="system", work_item_id=work_item_id, operator_user_id=member
    )
    user_turns = [t for t in snapshot.turns if t.role == ConversationTurnRole.USER]
    assert len(user_turns) == 1
    assert user_turns[0].text == user_text


async def test_hitl_operator_chat_rejects_unauthorized_and_non_takeover_send(
    app, di, unique_id
):
    """Не член очереди не пишет; single_reply запрещает ask-append (ответ через complete)."""
    slug = f"hitlchat2-{unique_id}"
    await di.work_item_service.create_queue(
        company_id="system", name="HITLChat2", slug=slug
    )
    state = _hitl_state(unique_id)
    await di.workflow_runtime.save_state(state.session_id, state)
    command = _hitl_command(unique_id)
    _cid, work_item_id = await di.node_constructor.hitl_work_item_service.register_handoff(
        state,
        question="q",
        task_title="t",
        assignee_queue_slug=slug,
        handoff_mode=HandoffMode.SINGLE_REPLY,
        command=command,
    )

    conv = di.hitl_conversation_service
    with pytest.raises(PermissionError):
        await conv.append_operator_message(
            company_id="system",
            work_item_id=work_item_id,
            operator_user_id=f"outsider_{unique_id}",
            text="hi",
            idempotency_key="k1",
        )

    member = f"op_{unique_id}"
    await di.work_item_service.add_queue_member(
        company_id="system",
        work_queue_id=(await WorkItem.require_in_company("system", work_item_id)).assignment.work_queue_id,
        member=UserActor(user_id=member),
    )
    await di.work_item_service.claim(
        company_id="system", work_item_id=work_item_id, user_id=member
    )
    # single_reply: ask-append запрещён (ответ только через complete / closing reply)
    with pytest.raises(ValueError):
        await conv.append_operator_message(
            company_id="system",
            work_item_id=work_item_id,
            operator_user_id=member,
            text="hi",
            idempotency_key="k2",
        )


# ============================ Агентские тулы (fire-and-forget / self) ============================


async def test_agent_tool_creates_self_assigned_job(app, di, unique_id):
    flow_id = f"agent_{unique_id}"
    await provision_flow_employee_for_tests(
        flow_id=flow_id,
        curator_user_id=f"cur_{unique_id}",
    )
    try:
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
        item = await WorkItem.require_in_company("system", work_item_id)
        assert item.kind is WorkItemKind.AGENT_JOB
        assert item.blocking is False
        assert isinstance(item.assignment, UsersAssignment)
        assert item.assignment.user_ids == [flow_employee_user_id(flow_id)]

        listed = await work_item_list.run({"state_filter": "open"}, state)
        assert any(row["work_item_id"] == work_item_id for row in listed["items"])

        done = await work_item_complete.run(
            {"work_item_id": work_item_id, "resolution_text": "finished"}, state
        )
        assert done["state"] == WorkItemState.DONE.value
    finally:
        await cleanup_flow_employee_for_tests(flow_id=flow_id)


async def test_agent_tool_queue_assignment_requires_existing_queue(app, di, unique_id):
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
    entity = CRMEntity(
        entity_id=f"ent_{unique_id}",
        company_id="system",
        namespace=f"crm-ns-{unique_id}",
        entity_type="task",
        name=f"CRM task {unique_id}",
        user_id="test_user",
        attributes={},
    )
    return await CRMEntity.create(entity)


async def test_crm_task_pairs_with_work_item_and_kernel_owns_state(app, di, unique_id):
    crm_entity = await _create_crm_task_entity(unique_id)
    svc = di.work_item_service
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
    refreshed = await CRMEntity.get(crm_entity.entity_id)
    assert refreshed is not None
    assert refreshed.entity_type == "task"
    assert refreshed.status == "active"


async def test_crm_task_work_item_visible_in_namespace_list(app, di, unique_id):
    crm_entity = await _create_crm_task_entity(unique_id)
    svc = di.work_item_service
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


async def test_reassign_between_user_agent_queue(app, di, unique_id):
    """Любая задача переназначается на человека/агента/очередь в любой момент."""
    agent_flow_id = f"flow_{unique_id}"
    await provision_flow_employee_for_tests(
        flow_id=agent_flow_id,
        curator_user_id=f"cur_{unique_id}",
    )
    try:
        svc = di.work_item_service
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
            assignment=UsersAssignment(user_ids=[flow_employee_user_id(agent_flow_id)]),
        )
        assert isinstance(to_agent.assignment, UsersAssignment)

        to_queue = await svc.reassign(
            company_id="system",
            work_item_id=item.work_item_id,
            assignment=QueueAssignment(work_queue_id=queue.work_queue_id),
        )
        assert isinstance(to_queue.assignment, QueueAssignment)
    finally:
        await cleanup_flow_employee_for_tests(flow_id=agent_flow_id)


async def test_reassign_terminal_raises(app, di, unique_id):
    svc = di.work_item_service
    item = await svc.create(
        company_id="system", title=f"term-reassign-{unique_id}", created_by=SystemActor()
    )
    _ = await svc.complete(company_id="system", work_item_id=item.work_item_id)
    with pytest.raises(ValueError):
        await svc.reassign(
            company_id="system",
            work_item_id=item.work_item_id,
            assignment=UsersAssignment(user_ids=[flow_employee_user_id("f")]),
        )


async def test_cancel_and_reject_terminal_states(app, di, unique_id):
    svc = di.work_item_service
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


async def test_hooks_metadata_persisted_without_http_dispatch(app, di, unique_id):
    """hooks хранят binding для bus-потребителей; HTTP dispatcher удалён."""
    agent_flow_id = f"flow_{unique_id}"
    await provision_flow_employee_for_tests(
        flow_id=agent_flow_id,
        curator_user_id=f"cur_{unique_id}",
    )
    try:
        svc = WorkItemService(
            repository=di.worktracker_repository,
            queue_access=WorkQueueAccessService(di.authz_service),
            authz=di.authz_service,
        )
        hooks = [
            WorkItemHook(
                event=WorkItemHookEvent.COMPLETED,
                service="flows",
                path="platform:events",
                binding={"probe": unique_id},
            ),
        ]
        item = await svc.create(
            company_id="system",
            title=f"hooks-{unique_id}",
            created_by=SystemActor(),
            kind=WorkItemKind.AGENT_JOB,
            assignment=UsersAssignment(user_ids=[flow_employee_user_id(agent_flow_id)]),
            hooks=hooks,
        )
        loaded = await svc.get("system", item.work_item_id)
        completed = loaded.hooks_for(WorkItemHookEvent.COMPLETED)
        assert len(completed) == 1
        assert completed[0].binding["probe"] == unique_id
        assert completed[0].path == "platform:events"

        _ = await svc.complete(company_id="system", work_item_id=item.work_item_id)
        done = await svc.get("system", item.work_item_id)
        assert done.state in TERMINAL_WORK_ITEM_STATES
    finally:
        await cleanup_flow_employee_for_tests(flow_id=agent_flow_id)


async def test_work_item_attachments_variables_comment_files_roundtrip(app, di, unique_id):
    svc = di.work_item_service
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


async def test_reassign_publishes_assigned_bus_event(
    app, di, platform_events_listener, unique_id
):
    from core.worktracker.events import WORK_ITEM_ASSIGNED

    agent_flow_id = f"flow_{unique_id}"
    await provision_flow_employee_for_tests(
        flow_id=agent_flow_id,
        curator_user_id=f"cur_{unique_id}",
    )
    try:
        svc = di.work_item_service
        item = await svc.create(
            company_id="system",
            title=f"reassign-hook-{unique_id}",
            created_by=SystemActor(),
        )
        await svc.reassign(
            company_id="system",
            work_item_id=item.work_item_id,
            assignment=UsersAssignment(user_ids=[flow_employee_user_id(agent_flow_id)]),
        )
        events = await platform_events_listener(WORK_ITEM_ASSIGNED, None, 3.0)
        matched = [
            event
            for event in events
            if isinstance(event.get("payload"), dict)
            and isinstance(event["payload"].get("work_item"), dict)
            and event["payload"]["work_item"].get("work_item_id") == item.work_item_id
        ]
        assert matched, "ожидалось worktracker/work_item/assigned после reassign"
    finally:
        await cleanup_flow_employee_for_tests(flow_id=agent_flow_id)
