"""
Интеграционные тесты операторского handoff: БД, OperatorHandoffService, hitl_node,
LLM + hitl_operator_task, API, resume после complete, Redis stream (нефинальный interrupt).

Мок только MockLLM. Репозитории, Redis, TaskIQ .kiq через sync_tools — без unittest.mock.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from a2a.types import TaskState, TaskStatusUpdateEvent
from a2a.utils.message import get_message_text
from httpx import ASGITransport, AsyncClient

from apps.flows.main import app as flows_app
from apps.flows.src.models.flow_config import Edge, FlowConfig
from apps.flows.src.streaming.subscriber import EventSubscriber
from apps.flows.src.tasks.flow_tasks import process_flow_task
from core.context import Context, clear_context, set_context
from core.files.models import FileRecord, FileStatus
from core.state import ExecutionState
from core.state.interrupt import InterruptKind


def _context_a2a(mock_context: Context) -> Context:
    """Канал a2a нужен для get_channel и для snapshot в complete_handoff."""
    return mock_context.model_copy(update={"channel": "a2a"})


@pytest.mark.asyncio
async def test_hitl_node_creates_operator_task_and_operator_interrupt(
    app, container, unique_id, mock_context
):
    slug = f"hitl_{unique_id}"
    repo = container.operator_repository
    qid = await repo.create_queue(company_id="system", name="Queue", slug=slug)
    await repo.add_member(qid, mock_context.user.user_id)

    flow_id = f"op_hitl_{unique_id}"
    cfg = FlowConfig(
        flow_id=flow_id,
        name="hitl only",
        entry="h",
        nodes={
            "h": {
                "type": "hitl_node",
                "operator_queue_slug": slug,
                "operator_task_title": "Support",
                "operator_user_message": "Operator will join",
            }
        },
        edges=[Edge(from_node="h", to_node=None)],
    )
    await container.flow_repository.set(cfg)

    ctx_part = f"ctx-{unique_id}"
    session_id = f"{flow_id}:{ctx_part}"
    mock_context.session_id = session_id
    task_a2a = f"a2a-{unique_id}"
    ctx = _context_a2a(mock_context)

    set_context(ctx)
    try:
        out = await process_flow_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=ctx.user.user_id,
            content="hello",
            task_id=task_a2a,
            context_id=ctx_part,
            context_data=ctx.model_dump(),
            channel="a2a",
        )
    finally:
        clear_context()

    assert out["task_state"] == "input-required"
    assert out["interrupt"] is not None
    assert out["interrupt"]["body"]["kind"] == InterruptKind.OPERATOR_TASK.value

    cid = out["interrupt"].get("correlation_id")
    assert cid
    row = await repo.get_task_by_correlation("system", str(cid))
    assert row is not None
    assert row.session_id == session_id
    assert row.a2a_task_id == task_a2a
    assert row.flow_id == flow_id
    assert row.interrupt_snapshot is not None
    assert row.interrupt_snapshot.get("assignee_queue") == slug


@pytest.mark.asyncio
async def test_hitl_node_unknown_queue_slug_raises(
    app, container, unique_id, mock_context
):
    flow_id = f"op_badq_{unique_id}"
    cfg = FlowConfig(
        flow_id=flow_id,
        name="bad queue",
        entry="h",
        nodes={
            "h": {
                "type": "hitl_node",
                "operator_queue_slug": f"missing_{unique_id}",
                "operator_task_title": "T",
                "operator_user_message": "M",
            }
        },
        edges=[Edge(from_node="h", to_node=None)],
    )
    await container.flow_repository.set(cfg)

    ctx_part = f"ctx-{unique_id}"
    session_id = f"{flow_id}:{ctx_part}"
    mock_context.session_id = session_id
    ctx = _context_a2a(mock_context)

    set_context(ctx)
    try:
        with pytest.raises(ValueError, match="не найдена|slug|очередь"):
            await process_flow_task(
                flow_id=flow_id,
                session_id=session_id,
                user_id=ctx.user.user_id,
                content="x",
                task_id=f"t-{unique_id}",
                context_id=ctx_part,
                context_data=ctx.model_dump(),
                channel="a2a",
            )
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_register_handoff_same_correlation_inserts_single_row(
    app, container, unique_id, mock_context
):
    slug = f"idemp_{unique_id}"
    repo = container.operator_repository
    qid = await repo.create_queue(company_id="system", name="N", slug=slug)
    await repo.add_member(qid, mock_context.user.user_id)
    svc = container.operator_handoff_service
    cid = uuid.uuid4()
    state = ExecutionState(
        task_id=f"t-{unique_id}",
        context_id=f"ctx-{unique_id}",
        user_id=mock_context.user.user_id,
        session_id=f"fid_{unique_id}:ctx-{unique_id}",
    )
    ctx = _context_a2a(mock_context)
    set_context(ctx)
    try:
        await svc.register_handoff(
            state,
            question="q",
            task_title="ttl",
            assignee_queue_slug=slug,
            correlation_id=cid,
        )
        await svc.register_handoff(
            state,
            question="q2",
            task_title="ttl2",
            assignee_queue_slug=slug,
            correlation_id=cid,
        )
    finally:
        clear_context()

    rows, total = await repo.list_tasks("system", queue_id=qid)
    assert total == 1
    assert rows[0].correlation_id == str(cid)


@pytest.mark.asyncio
@pytest.mark.timeout(25)
async def test_operator_handoff_first_stream_event_nonfinal_with_handoff_flag(
    app, container, unique_id, mock_context
):
    slug = f"stream_{unique_id}"
    repo = container.operator_repository
    qid = await repo.create_queue(company_id="system", name="S", slug=slug)
    await repo.add_member(qid, mock_context.user.user_id)

    flow_id = f"op_stream_{unique_id}"
    cfg = FlowConfig(
        flow_id=flow_id,
        name="stream",
        entry="h",
        nodes={
            "h": {
                "type": "hitl_node",
                "operator_queue_slug": slug,
                "operator_task_title": "T",
                "operator_user_message": "Wait",
            }
        },
        edges=[Edge(from_node="h", to_node=None)],
    )
    await container.flow_repository.set(cfg)

    ctx_part = f"ctx-{unique_id}"
    session_id = f"{flow_id}:{ctx_part}"
    task_id = f"streamtid-{unique_id}"
    mock_context.session_id = session_id
    ctx = _context_a2a(mock_context)

    ready = asyncio.Event()
    collected: list = []

    async def listen() -> None:
        sub = EventSubscriber(container.redis_client)
        async for ev in sub.subscribe(task_id, timeout=3.0, ready_event=ready):
            collected.append(ev)

    listen_task = asyncio.create_task(listen())
    await asyncio.wait_for(ready.wait(), timeout=5.0)

    set_context(ctx)
    try:
        await process_flow_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=ctx.user.user_id,
            content="hi",
            task_id=task_id,
            context_id=ctx_part,
            context_data=ctx.model_dump(),
            channel="a2a",
        )
    finally:
        clear_context()

    await asyncio.wait_for(listen_task, timeout=10.0)

    status_events = [e for e in collected if isinstance(e, TaskStatusUpdateEvent)]
    assert status_events, "ожидалось хотя бы одно status-update в Redis stream"
    op_ev = next(
        (
            e
            for e in status_events
            if e.status and e.status.state == TaskState.input_required
        ),
        None,
    )
    assert op_ev is not None
    assert op_ev.final is False
    assert (op_ev.metadata or {}).get("platform_handoff_continue") is True


@pytest.mark.asyncio
async def test_llm_hitl_operator_task_then_complete_resumes_and_finishes(
    app,
    container,
    client,
    unique_id,
    mock_context,
    mock_llm_with_queue,
    system_user_id,
):
    slug = f"llmhq_{unique_id}"
    r_create = await client.post(
        "/flows/api/v1/operator/queues",
        json={"name": "L", "slug": slug},
    )
    assert r_create.status_code == 200, r_create.text

    hitl_ref = await container.tool_repository.get("hitl_operator_task")
    if hitl_ref is None:
        raise RuntimeError("hitl_operator_task должен быть в tool_repository после load_tools_to_db")
    hitl_inline = hitl_ref.model_dump(exclude_none=True)

    flow_id = f"op_llm_{unique_id}"
    cfg = FlowConfig(
        flow_id=flow_id,
        name="llm handoff",
        entry="main",
        nodes={
            "main": {
                "type": "llm_node",
                "prompt": (
                    "You must call tool hitl_operator_task exactly once with "
                    f'assignee_queue="{slug}", task_title="Escalation", question="Need human".'
                ),
                "tools": [hitl_inline],
            }
        },
        edges=[Edge(from_node="main", to_node=None)],
    )
    await container.flow_repository.set(cfg)

    mock_llm_with_queue(
        [
            {
                "type": "tool_call",
                "tool": "hitl_operator_task",
                "args": {
                    "question": "Need human",
                    "task_title": "Escalation",
                    "assignee_queue": slug,
                },
            },
            {"type": "text", "content": "Resumed and done"},
        ]
    )

    ctx_part = f"ctx-{unique_id}"
    session_id = f"{flow_id}:{ctx_part}"
    task_a2a = f"a2a-{unique_id}"
    mock_context.session_id = session_id
    mock_context.user.user_id = system_user_id
    ctx = _context_a2a(mock_context)

    first = await process_flow_task(
        flow_id=flow_id,
        session_id=session_id,
        user_id=system_user_id,
        content="user msg",
        task_id=task_a2a,
        context_id=ctx_part,
        context_data=ctx.model_dump(),
        channel="a2a",
    )
    assert first["task_state"] == "input-required"
    assert first["interrupt"]["body"]["kind"] == InterruptKind.OPERATOR_TASK.value

    tasks_body = await client.get("/flows/api/v1/operator/tasks")
    assert tasks_body.status_code == 200
    tasks = tasks_body.json()["items"]
    op_task = next((t for t in tasks if t.get("session_id") == session_id), None)
    assert op_task is not None, "задача оператора должна быть видна участнику очереди"

    done = await client.post(
        f"/flows/api/v1/operator/tasks/{op_task['id']}/complete",
        json={"resolution": "operator answer text"},
    )
    assert done.status_code == 200, done.text

    set_context(ctx)
    try:
        saved = await container.state_manager.get_state(session_id)
    finally:
        clear_context()
    assert saved is not None
    assert not saved.interrupt

    assert saved.response and "Resumed" in saved.response


@pytest.mark.asyncio
async def test_operator_non_member_forbidden_get_task_by_id(
    app,
    container,
    client,
    unique_id,
    mock_context,
    auth_headers_system_user2,
):
    slug = f"acl_{unique_id}"
    r_create = await client.post(
        "/flows/api/v1/operator/queues",
        json={"name": "ACL", "slug": slug},
    )
    assert r_create.status_code == 200

    flow_id = f"op_acl_{unique_id}"
    cfg = FlowConfig(
        flow_id=flow_id,
        name="acl",
        entry="h",
        nodes={
            "h": {
                "type": "hitl_node",
                "operator_queue_slug": slug,
                "operator_task_title": "T",
                "operator_user_message": "M",
            }
        },
        edges=[Edge(from_node="h", to_node=None)],
    )
    await container.flow_repository.set(cfg)

    ctx_part = f"ctx-{unique_id}"
    session_id = f"{flow_id}:{ctx_part}"
    mock_context.session_id = session_id
    ctx = _context_a2a(mock_context)

    set_context(ctx)
    try:
        await process_flow_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=ctx.user.user_id,
            content="x",
            task_id=f"t-{unique_id}",
            context_id=ctx_part,
            context_data=ctx.model_dump(),
            channel="a2a",
        )
    finally:
        clear_context()

    mine = await client.get("/flows/api/v1/operator/tasks")
    assert mine.status_code == 200
    tid = mine.json()["items"][0]["id"]

    transport = ASGITransport(app=flows_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=auth_headers_system_user2,
    ) as u2:
        forbidden = await u2.get(f"/flows/api/v1/operator/tasks/{tid}")
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_operator_claim_and_patch_status(
    app, container, client, unique_id, mock_context
):
    slug = f"claim_{unique_id}"
    await client.post("/flows/api/v1/operator/queues", json={"name": "C", "slug": slug})

    flow_id = f"op_claim_{unique_id}"
    cfg = FlowConfig(
        flow_id=flow_id,
        name="claim",
        entry="h",
        nodes={
            "h": {
                "type": "hitl_node",
                "operator_queue_slug": slug,
                "operator_task_title": "T",
                "operator_user_message": "M",
            }
        },
        edges=[Edge(from_node="h", to_node=None)],
    )
    await container.flow_repository.set(cfg)

    ctx_part = f"ctx-{unique_id}"
    session_id = f"{flow_id}:{ctx_part}"
    mock_context.session_id = session_id
    ctx = _context_a2a(mock_context)

    set_context(ctx)
    try:
        await process_flow_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=ctx.user.user_id,
            content="x",
            task_id=f"tk-{unique_id}",
            context_id=ctx_part,
            context_data=ctx.model_dump(),
            channel="a2a",
        )
    finally:
        clear_context()

    lst = await client.get("/flows/api/v1/operator/tasks")
    tid = lst.json()["items"][0]["id"]

    cl = await client.post(f"/flows/api/v1/operator/tasks/{tid}/claim")
    assert cl.status_code == 200
    assert cl.json()["status"] == "claimed"

    patch = await client.patch(
        f"/flows/api/v1/operator/tasks/{tid}",
        json={"status": "awaiting_agent"},
    )
    assert patch.status_code == 200
    assert patch.json()["status"] == "awaiting_agent"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_full_hitl_dialogue_single_reply_then_takeover_then_followup(
    app,
    container,
    client,
    unique_id,
    mock_context,
    mock_llm_with_queue,
    system_user_id,
):
    """Полный сценарий HITL по мотивам реального диалога:

    1) single_reply: LLM → hitl_operator_task → operator completes → LLM резюмирует
    2) takeover: LLM → hitl_operator_task(takeover) → оператор + юзер переписываются
       через A2A message/send (dialog_log) → complete → LLM получает лог в tool_result
    3) follow-up: юзер спрашивает об ответе оператора → LLM отвечает из контекста
    """
    slug = f"full_{unique_id}"
    await client.post("/flows/api/v1/operator/queues", json={"name": "Full", "slug": slug})

    hitl_ref = await container.tool_repository.get("hitl_operator_task")
    if hitl_ref is None:
        raise RuntimeError("hitl_operator_task не найден в tool_repository")
    hitl_inline = hitl_ref.model_dump(exclude_none=True)

    flow_id = f"full_hitl_{unique_id}"
    cfg = FlowConfig(
        flow_id=flow_id,
        name="full hitl",
        entry="main",
        nodes={
            "main": {
                "type": "llm_node",
                "prompt": "You are an assistant with hitl_operator_task tool.",
                "tools": [hitl_inline],
            }
        },
        edges=[Edge(from_node="main", to_node=None)],
    )
    await container.flow_repository.set(cfg)

    ctx_part = f"ctx-{unique_id}"
    session_id = f"{flow_id}:{ctx_part}"
    task_a2a = f"a2a-full-{unique_id}"
    mock_context.session_id = session_id
    mock_context.user.user_id = system_user_id
    ctx = _context_a2a(mock_context)

    # --- Фаза 1: single_reply ---
    mock_llm_with_queue([
        {
            "type": "tool_call",
            "tool": "hitl_operator_task",
            "args": {
                "question": "Где живут белые медведи?",
                "task_title": "Белые медведи",
                "assignee_queue": slug,
            },
        },
        {"type": "text", "content": "Оператор ответил: в Арктике."},
    ])

    set_context(ctx)
    try:
        first = await process_flow_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=system_user_id,
            content="спроси у оператора где живут белые медведи",
            task_id=task_a2a,
            context_id=ctx_part,
            context_data=ctx.model_dump(),
            channel="a2a",
        )
    finally:
        clear_context()
    assert first["task_state"] == "input-required"
    assert first["interrupt"]["body"]["kind"] == InterruptKind.OPERATOR_TASK.value
    assert first["interrupt"]["body"].get("handoff_mode", "single_reply") == "single_reply"

    tasks_resp = await client.get("/flows/api/v1/operator/tasks")
    op_task_sr = next(
        t for t in tasks_resp.json()["items"] if t["session_id"] == session_id
    )
    tid_sr = op_task_sr["id"]

    done_sr = await client.post(
        f"/flows/api/v1/operator/tasks/{tid_sr}/complete",
        json={"resolution": "в Арктике"},
    )
    assert done_sr.status_code == 200

    set_context(ctx)
    try:
        saved_sr = await container.state_manager.get_state(session_id)
    finally:
        clear_context()
    assert saved_sr is not None
    assert saved_sr.interrupt is None
    assert "Арктике" in saved_sr.response

    # tool_call/tool_result паринг: после assistant+tool_calls сразу agent+tool_call_id
    msgs = saved_sr.messages
    tc_idx = next(
        i for i, m in enumerate(msgs)
        if (m.metadata or {}).get("tool_calls")
        and any(tc.get("name") == "hitl_operator_task" for tc in m.metadata["tool_calls"])
    )
    tr_msg = msgs[tc_idx + 1]
    assert (tr_msg.metadata or {}).get("tool_call_id"), (
        "после assistant+tool_calls должен идти tool_result"
    )

    # --- Фаза 2: takeover ---
    mock_llm_with_queue([
        {
            "type": "tool_call",
            "tool": "hitl_operator_task",
            "args": {
                "question": "Где живут белки?",
                "task_title": "Белки",
                "assignee_queue": slug,
                "handoff_mode": "takeover",
            },
        },
        {"type": "text", "content": "Оператор сообщил: в дуплах."},
    ])

    set_context(ctx)
    try:
        second = await process_flow_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=system_user_id,
            content="передай оператору, где живут белки, handover",
            task_id=task_a2a,
            context_id=ctx_part,
            context_data=ctx.model_dump(),
            channel="a2a",
            is_resume=True,
        )
    finally:
        clear_context()
    assert second["task_state"] == "input-required"
    assert second["interrupt"]["body"]["handoff_mode"] == "takeover"

    tasks_resp2 = await client.get("/flows/api/v1/operator/tasks")
    op_task_tk = next(
        t
        for t in tasks_resp2.json()["items"]
        if t["session_id"] == session_id and t["id"] != tid_sr
    )
    tid_tk = op_task_tk["id"]
    assert op_task_tk["handoff_mode"] == "takeover"

    await client.post(f"/flows/api/v1/operator/tasks/{tid_tk}/claim")

    # Оператор отправляет сообщение юзеру
    msg_resp = await client.post(
        f"/flows/api/v1/operator/tasks/{tid_tk}/messages",
        json={"text": "В дупле дерева"},
    )
    assert msg_resp.status_code == 200

    # Юзер отвечает через A2A message/send (follow-up при input-required)
    a2a_reply = await client.post(
        f"/flows/api/v1/{flow_id}",
        json={
            "jsonrpc": "2.0",
            "id": "user-reply-1",
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": f"ur1-{unique_id}",
                    "role": "user",
                    "parts": [{"kind": "text", "text": "а это где именно?"}],
                    "contextId": ctx_part,
                },
            },
        },
    )
    assert a2a_reply.status_code == 200
    reply_result = a2a_reply.json()["result"]
    assert reply_result["status"]["state"] == "input-required", (
        "A2A follow-up при takeover должен вернуть input-required"
    )

    # Реплика юзера попала в dialog_log
    detail = await client.get(f"/flows/api/v1/operator/tasks/{tid_tk}")
    log = detail.json().get("dialog_log", [])
    assert len(log) == 2
    assert log[0]["role"] == "operator"
    assert log[0]["text"] == "В дупле дерева"
    assert log[1]["role"] == "user"
    assert log[1]["text"] == "а это где именно?"

    # Оператор отвечает ещё раз
    await client.post(
        f"/flows/api/v1/operator/tasks/{tid_tk}/messages",
        json={"text": "в лесу, в дупле дуба"},
    )

    # Юзер подтверждает через A2A
    a2a_reply2 = await client.post(
        f"/flows/api/v1/{flow_id}",
        json={
            "jsonrpc": "2.0",
            "id": "user-reply-2",
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": f"ur2-{unique_id}",
                    "role": "user",
                    "parts": [{"kind": "text", "text": "понял спасибо"}],
                    "contextId": ctx_part,
                },
            },
        },
    )
    assert a2a_reply2.status_code == 200

    detail2 = await client.get(f"/flows/api/v1/operator/tasks/{tid_tk}")
    log2 = detail2.json().get("dialog_log", [])
    assert len(log2) == 4

    # Оператор завершает и возвращает управление агенту
    done_tk = await client.post(
        f"/flows/api/v1/operator/tasks/{tid_tk}/complete",
        json={"resolution": "ответил пользователю про белок"},
    )
    assert done_tk.status_code == 200

    set_context(ctx)
    try:
        saved_tk = await container.state_manager.get_state(session_id)
    finally:
        clear_context()
    assert saved_tk.interrupt is None
    assert "дупл" in saved_tk.response.lower()

    # tool_call/tool_result паринг для takeover
    tk_msgs = saved_tk.messages
    tc2_idx = next(
        i for i, m in enumerate(tk_msgs)
        if (m.metadata or {}).get("tool_calls")
        and any(
            tc.get("arguments", {}).get("handoff_mode") == "takeover"
            for tc in m.metadata["tool_calls"]
        )
    )
    tr2_msg = tk_msgs[tc2_idx + 1]
    assert (tr2_msg.metadata or {}).get("tool_call_id"), (
        "после takeover tool_call должен идти tool_result"
    )
    # dialog_log отформатирован как текст в tool_result, не как отдельные messages
    tr2_text = get_message_text(tr2_msg)
    assert "[Оператор]:" in tr2_text
    assert "[Пользователь]:" in tr2_text
    assert "В дупле дерева" in tr2_text
    assert "а это где именно?" in tr2_text

    # --- Фаза 3: follow-up ---
    mock_llm_with_queue([
        {"type": "text", "content": "Белки живут в дуплах деревьев, как сообщил оператор."},
    ])

    set_context(ctx)
    try:
        followup = await process_flow_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=system_user_id,
            content="так в итоге где живут белки?",
            task_id=task_a2a,
            context_id=ctx_part,
            context_data=ctx.model_dump(),
            channel="a2a",
            is_resume=True,
        )
    finally:
        clear_context()
    assert followup["task_state"] == "completed"

    set_context(ctx)
    try:
        saved_final = await container.state_manager.get_state(session_id)
    finally:
        clear_context()
    assert "дупл" in saved_final.response.lower()
    assert saved_final.interrupt is None


@pytest.mark.asyncio
async def test_operator_post_message_member_sends_and_non_member_forbidden(
    app,
    container,
    client,
    unique_id,
    mock_context,
    auth_headers_system_user2,
):
    slug = f"msg_{unique_id}"
    await client.post("/flows/api/v1/operator/queues", json={"name": "M", "slug": slug})

    flow_id = f"op_msg_{unique_id}"
    cfg = FlowConfig(
        flow_id=flow_id,
        name="msg",
        entry="h",
        nodes={
            "h": {
                "type": "hitl_node",
                "operator_queue_slug": slug,
                "operator_task_title": "T",
                "operator_user_message": "M",
                "operator_handoff_mode": "takeover",
            }
        },
        edges=[Edge(from_node="h", to_node=None)],
    )
    await container.flow_repository.set(cfg)

    ctx_part = f"ctx-{unique_id}"
    session_id = f"{flow_id}:{ctx_part}"
    a2a = f"a2a-msg-{unique_id}"
    mock_context.session_id = session_id
    ctx = _context_a2a(mock_context)

    set_context(ctx)
    try:
        await process_flow_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=ctx.user.user_id,
            content="x",
            task_id=a2a,
            context_id=ctx_part,
            context_data=ctx.model_dump(),
            channel="a2a",
        )
    finally:
        clear_context()

    lst = await client.get("/flows/api/v1/operator/tasks")
    tid = lst.json()["items"][0]["id"]

    transport = ASGITransport(app=flows_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=auth_headers_system_user2,
    ) as u2:
        forbidden = await u2.post(
            f"/flows/api/v1/operator/tasks/{tid}/messages",
            json={"text": "from outsider"},
        )
    assert forbidden.status_code == 403

    await client.post(f"/flows/api/v1/operator/tasks/{tid}/claim")

    ok = await client.post(
        f"/flows/api/v1/operator/tasks/{tid}/messages",
        json={"text": "Hello from operator"},
    )
    assert ok.status_code == 200, ok.text

    detail = await client.get(f"/flows/api/v1/operator/tasks/{tid}")
    assert detail.status_code == 200
    assert detail.json()["task"]["status"] == "user_dialog"

    log = detail.json().get("dialog_log", [])
    assert len(log) == 1
    assert log[0]["role"] == "operator"
    assert log[0]["text"] == "Hello from operator"


@pytest.mark.asyncio
@pytest.mark.timeout(25)
async def test_hitl_node_single_reply_graph(
    app, container, client, unique_id, mock_context
):
    """hitl_node на графе: single_reply — оператор отвечает один раз,
    flow продолжает к следующей ноде (formatter)."""
    slug = f"gsr_{unique_id}"
    await client.post(
        "/flows/api/v1/operator/queues", json={"name": "GSR", "slug": slug}
    )

    flow_id = f"g_sr_{unique_id}"
    cfg = FlowConfig(
        flow_id=flow_id,
        name="graph single_reply",
        entry="hitl",
        nodes={
            "hitl": {
                "type": "hitl_node",
                "operator_queue_slug": slug,
                "operator_task_title": "SR",
                "operator_user_message": "Ожидайте ответа.",
                "operator_handoff_mode": "single_reply",
            },
            "fmt": {
                "type": "code",
                "code": (
                    "async def run(args, state):\n"
                    "    state['response'] = f\"[FMT] {state.get('response', '')}\"\n"
                    "    return state"
                ),
            },
        },
        edges=[
            Edge(from_node="hitl", to_node="fmt"),
            Edge(from_node="fmt", to_node=None),
        ],
    )
    await container.flow_repository.set(cfg)

    ctx_part = f"ctx-{unique_id}"
    session_id = f"{flow_id}:{ctx_part}"
    mock_context.session_id = session_id
    ctx = _context_a2a(mock_context)

    set_context(ctx)
    try:
        first = await process_flow_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=ctx.user.user_id,
            content="нужен оператор",
            task_id=f"t-{unique_id}",
            context_id=ctx_part,
            context_data=ctx.model_dump(),
            channel="a2a",
        )
    finally:
        clear_context()

    assert first["task_state"] == "input-required"
    assert first["interrupt"]["body"]["kind"] == InterruptKind.OPERATOR_TASK.value
    assert first["interrupt"]["body"].get("handoff_mode", "single_reply") == "single_reply"

    tasks_resp = await client.get("/flows/api/v1/operator/tasks")
    op_task = next(
        t for t in tasks_resp.json()["items"] if t["session_id"] == session_id
    )
    assert op_task["handoff_mode"] == "single_reply"

    done = await client.post(
        f"/flows/api/v1/operator/tasks/{op_task['id']}/complete",
        json={"resolution": "Арктика"},
    )
    assert done.status_code == 200

    set_context(ctx)
    try:
        saved = await container.state_manager.get_state(session_id)
    finally:
        clear_context()

    assert saved.interrupt is None
    assert saved.response is not None
    assert "[FMT]" in saved.response, "formatter нода должна была отработать после hitl"
    assert "Арктика" in saved.response


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_hitl_node_takeover_graph(
    app, container, client, unique_id, mock_context
):
    """hitl_node на графе: takeover — оператор ведёт диалог с юзером через
    A2A follow-up, потом complete → flow продолжает с dialog_log в content."""
    slug = f"gtk_{unique_id}"
    await client.post(
        "/flows/api/v1/operator/queues", json={"name": "GTK", "slug": slug}
    )

    flow_id = f"g_tk_{unique_id}"
    cfg = FlowConfig(
        flow_id=flow_id,
        name="graph takeover",
        entry="hitl",
        nodes={
            "hitl": {
                "type": "hitl_node",
                "operator_queue_slug": slug,
                "operator_task_title": "TK",
                "operator_user_message": "Оператор перехватил.",
                "operator_handoff_mode": "takeover",
            },
            "fmt": {
                "type": "code",
                "code": (
                    "async def run(args, state):\n"
                    "    state['response'] = f\"[FMT] {state.get('response', '')}\"\n"
                    "    return state"
                ),
            },
        },
        edges=[
            Edge(from_node="hitl", to_node="fmt"),
            Edge(from_node="fmt", to_node=None),
        ],
    )
    await container.flow_repository.set(cfg)

    ctx_part = f"ctx-{unique_id}"
    session_id = f"{flow_id}:{ctx_part}"
    task_a2a = f"t-{unique_id}"
    mock_context.session_id = session_id
    ctx = _context_a2a(mock_context)

    set_context(ctx)
    try:
        first = await process_flow_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=ctx.user.user_id,
            content="перехват диалога",
            task_id=task_a2a,
            context_id=ctx_part,
            context_data=ctx.model_dump(),
            channel="a2a",
        )
    finally:
        clear_context()

    assert first["task_state"] == "input-required"
    assert first["interrupt"]["body"]["handoff_mode"] == "takeover"

    tasks_resp = await client.get("/flows/api/v1/operator/tasks")
    op_task = next(
        t for t in tasks_resp.json()["items"] if t["session_id"] == session_id
    )
    tid = op_task["id"]
    assert op_task["handoff_mode"] == "takeover"

    await client.post(f"/flows/api/v1/operator/tasks/{tid}/claim")

    await client.post(
        f"/flows/api/v1/operator/tasks/{tid}/messages",
        json={"text": "Привет, чем помочь?"},
    )

    # Юзер отвечает через A2A message/send
    reply = await client.post(
        f"/flows/api/v1/{flow_id}",
        json={
            "jsonrpc": "2.0",
            "id": "ur1",
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": f"ur1-{unique_id}",
                    "role": "user",
                    "parts": [{"kind": "text", "text": "мне нужна консультация"}],
                    "contextId": ctx_part,
                },
            },
        },
    )
    assert reply.status_code == 200
    assert reply.json()["result"]["status"]["state"] == "input-required"

    # Проверяем dialog_log
    detail = await client.get(f"/flows/api/v1/operator/tasks/{tid}")
    log = detail.json().get("dialog_log", [])
    assert len(log) == 2
    assert log[0]["role"] == "operator"
    assert log[1]["role"] == "user"
    assert log[1]["text"] == "мне нужна консультация"

    await client.post(
        f"/flows/api/v1/operator/tasks/{tid}/messages",
        json={"text": "Рекомендую вариант А"},
    )

    done = await client.post(
        f"/flows/api/v1/operator/tasks/{tid}/complete",
        json={"resolution": "Клиенту рекомендован вариант А"},
    )
    assert done.status_code == 200

    set_context(ctx)
    try:
        saved = await container.state_manager.get_state(session_id)
    finally:
        clear_context()

    assert saved.interrupt is None
    assert saved.response is not None
    assert "[FMT]" in saved.response, "formatter должен отработать после hitl takeover"
    # dialog_log форматируется как текст в content при resume
    assert "Привет" in saved.response or "вариант А" in saved.response.lower()


async def _seed_file_record(container, unique_id: str, suffix: str = "") -> str:
    """Создаёт запись FileRecord в shared-репозитории и возвращает file_id."""
    fid = f"file-{unique_id}{suffix}"
    record = FileRecord(
        file_id=fid,
        provider="minio",
        original_name=f"test{suffix}.pdf",
        s3_key=f"test/{fid}",
        s3_bucket="default",
        content_type="application/pdf",
        file_size=1024,
        status=FileStatus.READY,
    )
    await container.file_repository.set(record)
    return fid


@pytest.mark.asyncio
async def test_operator_message_with_files_takeover(
    app, container, client, unique_id, mock_context
):
    """Оператор отправляет сообщение с file_ids в режиме takeover —
    file_ids сохраняются в dialog_log."""
    slug = f"fmsg_{unique_id}"
    await client.post("/flows/api/v1/operator/queues", json={"name": "FM", "slug": slug})

    file_id = await _seed_file_record(container, unique_id)

    flow_id = f"op_fmsg_{unique_id}"
    cfg = FlowConfig(
        flow_id=flow_id,
        name="file msg",
        entry="h",
        nodes={
            "h": {
                "type": "hitl_node",
                "operator_queue_slug": slug,
                "operator_task_title": "FM",
                "operator_user_message": "M",
                "operator_handoff_mode": "takeover",
            }
        },
        edges=[Edge(from_node="h", to_node=None)],
    )
    await container.flow_repository.set(cfg)

    ctx_part = f"ctx-{unique_id}"
    session_id = f"{flow_id}:{ctx_part}"
    mock_context.session_id = session_id
    ctx = _context_a2a(mock_context)

    set_context(ctx)
    try:
        await process_flow_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=ctx.user.user_id,
            content="x",
            task_id=f"a2a-{unique_id}",
            context_id=ctx_part,
            context_data=ctx.model_dump(),
            channel="a2a",
        )
    finally:
        clear_context()

    lst = await client.get("/flows/api/v1/operator/tasks")
    tid = lst.json()["items"][0]["id"]

    await client.post(f"/flows/api/v1/operator/tasks/{tid}/claim")

    resp = await client.post(
        f"/flows/api/v1/operator/tasks/{tid}/messages",
        json={"text": "See the attached", "file_ids": [file_id]},
    )
    assert resp.status_code == 200

    detail = await client.get(f"/flows/api/v1/operator/tasks/{tid}")
    log = detail.json().get("dialog_log", [])
    assert len(log) == 1
    assert log[0]["file_ids"] == [file_id]
    assert log[0]["text"] == "See the attached"


@pytest.mark.asyncio
async def test_operator_complete_with_files_single_reply(
    app, container, client, unique_id, mock_context,
    mock_llm_with_queue, system_user_id,
):
    """Оператор завершает single_reply с file_ids — ссылки попадают в content для LLM."""
    slug = f"fcomp_{unique_id}"
    await client.post("/flows/api/v1/operator/queues", json={"name": "FC", "slug": slug})

    file_id = await _seed_file_record(container, unique_id)

    hitl_ref = await container.tool_repository.get("hitl_operator_task")
    if hitl_ref is None:
        raise RuntimeError("hitl_operator_task не найден")
    hitl_inline = hitl_ref.model_dump(exclude_none=True)

    flow_id = f"op_fcomp_{unique_id}"
    cfg = FlowConfig(
        flow_id=flow_id,
        name="file complete sr",
        entry="main",
        nodes={
            "main": {
                "type": "llm_node",
                "prompt": "Call hitl_operator_task.",
                "tools": [hitl_inline],
            }
        },
        edges=[Edge(from_node="main", to_node=None)],
    )
    await container.flow_repository.set(cfg)

    mock_llm_with_queue([
        {
            "type": "tool_call",
            "tool": "hitl_operator_task",
            "args": {
                "question": "q",
                "task_title": "T",
                "assignee_queue": slug,
            },
        },
        {"type": "text", "content": "Done with files."},
    ])

    ctx_part = f"ctx-{unique_id}"
    session_id = f"{flow_id}:{ctx_part}"
    task_a2a = f"a2a-fcomp-{unique_id}"
    mock_context.session_id = session_id
    mock_context.user.user_id = system_user_id
    ctx = _context_a2a(mock_context)

    first = await process_flow_task(
        flow_id=flow_id,
        session_id=session_id,
        user_id=system_user_id,
        content="start",
        task_id=task_a2a,
        context_id=ctx_part,
        context_data=ctx.model_dump(),
        channel="a2a",
    )
    assert first["task_state"] == "input-required"

    tasks_resp = await client.get("/flows/api/v1/operator/tasks")
    op_task = next(
        t for t in tasks_resp.json()["items"] if t["session_id"] == session_id
    )

    done = await client.post(
        f"/flows/api/v1/operator/tasks/{op_task['id']}/complete",
        json={"resolution": "answer with attachment", "file_ids": [file_id]},
    )
    assert done.status_code == 200

    set_context(ctx)
    try:
        saved = await container.state_manager.get_state(session_id)
    finally:
        clear_context()
    assert saved.interrupt is None
    assert "Done" in saved.response


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_operator_complete_with_files_takeover_dialog_log(
    app, container, client, unique_id, mock_context
):
    """Takeover: оператор отправляет файлы, завершает с файлами — dialog_log содержит file_ids,
    format_dialog_log включает ссылки на download."""
    slug = f"ftk_{unique_id}"
    await client.post("/flows/api/v1/operator/queues", json={"name": "FTK", "slug": slug})

    fid1 = await _seed_file_record(container, unique_id, suffix="_a")
    fid2 = await _seed_file_record(container, unique_id, suffix="_b")

    flow_id = f"op_ftk_{unique_id}"
    cfg = FlowConfig(
        flow_id=flow_id,
        name="file takeover",
        entry="h",
        nodes={
            "h": {
                "type": "hitl_node",
                "operator_queue_slug": slug,
                "operator_task_title": "FTK",
                "operator_user_message": "M",
                "operator_handoff_mode": "takeover",
            },
            "fmt": {
                "type": "code",
                "code": (
                    "async def run(args, state):\n"
                    "    state['response'] = f\"[FMT] {state.get('response', '')}\"\n"
                    "    return state"
                ),
            },
        },
        edges=[
            Edge(from_node="h", to_node="fmt"),
            Edge(from_node="fmt", to_node=None),
        ],
    )
    await container.flow_repository.set(cfg)

    ctx_part = f"ctx-{unique_id}"
    session_id = f"{flow_id}:{ctx_part}"
    mock_context.session_id = session_id
    ctx = _context_a2a(mock_context)

    set_context(ctx)
    try:
        await process_flow_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=ctx.user.user_id,
            content="go",
            task_id=f"t-{unique_id}",
            context_id=ctx_part,
            context_data=ctx.model_dump(),
            channel="a2a",
        )
    finally:
        clear_context()

    lst = await client.get("/flows/api/v1/operator/tasks")
    tid = lst.json()["items"][0]["id"]
    await client.post(f"/flows/api/v1/operator/tasks/{tid}/claim")

    await client.post(
        f"/flows/api/v1/operator/tasks/{tid}/messages",
        json={"text": "here is the doc", "file_ids": [fid1]},
    )

    done = await client.post(
        f"/flows/api/v1/operator/tasks/{tid}/complete",
        json={"resolution": "final answer with attachment", "file_ids": [fid2]},
    )
    assert done.status_code == 200

    detail = await client.get(f"/flows/api/v1/operator/tasks/{tid}")
    log = detail.json().get("dialog_log", [])
    assert len(log) == 2
    assert log[0]["file_ids"] == [fid1]
    assert log[1]["file_ids"] == [fid2]

    from apps.flows.src.models.operator_schemas import OperatorDialogLogEntry
    from apps.flows.src.services.operator_handoff_service import OperatorHandoffService

    formatted = OperatorHandoffService._format_dialog_log_for_tool_result(
        [OperatorDialogLogEntry.model_validate(entry) for entry in log]
    )
    assert f"/flows/api/v1/files/download/{fid1}" in formatted
    assert f"/flows/api/v1/files/download/{fid2}" in formatted


@pytest.mark.asyncio
async def test_operator_message_invalid_file_id_raises(
    app, container, client, unique_id, mock_context
):
    """file_ids с несуществующим ID → 400 (ValueError из сервиса)."""
    slug = f"finv_{unique_id}"
    await client.post("/flows/api/v1/operator/queues", json={"name": "FI", "slug": slug})

    flow_id = f"op_finv_{unique_id}"
    cfg = FlowConfig(
        flow_id=flow_id,
        name="file invalid",
        entry="h",
        nodes={
            "h": {
                "type": "hitl_node",
                "operator_queue_slug": slug,
                "operator_task_title": "T",
                "operator_user_message": "M",
                "operator_handoff_mode": "takeover",
            }
        },
        edges=[Edge(from_node="h", to_node=None)],
    )
    await container.flow_repository.set(cfg)

    ctx_part = f"ctx-{unique_id}"
    session_id = f"{flow_id}:{ctx_part}"
    mock_context.session_id = session_id
    ctx = _context_a2a(mock_context)

    set_context(ctx)
    try:
        await process_flow_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=ctx.user.user_id,
            content="x",
            task_id=f"a2a-{unique_id}",
            context_id=ctx_part,
            context_data=ctx.model_dump(),
            channel="a2a",
        )
    finally:
        clear_context()

    lst = await client.get("/flows/api/v1/operator/tasks")
    tid = lst.json()["items"][0]["id"]
    await client.post(f"/flows/api/v1/operator/tasks/{tid}/claim")

    resp = await client.post(
        f"/flows/api/v1/operator/tasks/{tid}/messages",
        json={"text": "hi", "file_ids": ["nonexistent-file-id"]},
    )
    assert resp.status_code == 400
    assert "nonexistent-file-id" in resp.json()["detail"]
