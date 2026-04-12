"""
API операторских очередей и задач: /flows/api/v1/operator/...
"""

from __future__ import annotations

import asyncio
from typing import Any, List, Optional, Set

from fastapi import APIRouter, HTTPException, Query

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.db.models import OperatorQueues, OperatorTasks
from apps.flows.src.db.operator_repository import OperatorRepository
from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.services.operator_tasks_broadcast import publish_operator_tasks_refresh
from apps.flows.src.models.operator_schemas import (
    OperatorMemberAdd,
    OperatorQueueCreate,
    OperatorQueueOut,
    OperatorQueuePatch,
    OperatorTaskCompleteBody,
    OperatorTaskMessageBody,
    OperatorTaskOut,
    OperatorTaskPatch,
    OperatorTaskStatus,
)
from apps.flows.src.services.operator_handoff_service import parse_handoff_mode
from core.context import get_context
from core.logging import get_logger
from core.pagination import OffsetPage

logger = get_logger(__name__)

HANDOFF_PREVIEW_MAX_LEN = 200

router = APIRouter(tags=["operator"])


def _company_and_user() -> tuple[str, str]:
    ctx = get_context()
    if ctx is None or ctx.active_company is None or ctx.user is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация и активная компания")
    uid = str(ctx.user.user_id).strip()
    if not uid:
        raise HTTPException(status_code=401, detail="user_id в контексте пуст")
    return ctx.active_company.company_id, uid


def _company_operator_roles_normalized() -> Set[str]:
    ctx = get_context()
    if ctx is None or ctx.active_company is None or ctx.user is None:
        return set()
    company_id = ctx.active_company.company_id
    raw = ctx.user.companies.get(company_id)
    if raw is None:
        role_list: List[str] = []
    elif isinstance(raw, str):
        role_list = [raw]
    else:
        role_list = list(raw)
    return {str(r).strip().lower() for r in role_list if str(r).strip()}


def _require_operator_queue_manage_role() -> None:
    ctx = get_context()
    if ctx is None or ctx.active_company is None or ctx.user is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация и активная компания")
    normalized = _company_operator_roles_normalized()
    if not (normalized & {"admin", "owner"}):
        raise HTTPException(
            status_code=403,
            detail="Управление очередями оператора доступно только администраторам компании",
        )


def _queue_to_out(row: OperatorQueues, *, i_am_member: bool = False) -> OperatorQueueOut:
    return OperatorQueueOut(
        id=row.id,
        company_id=row.company_id,
        name=row.name,
        slug=row.slug,
        description=row.description,
        created_at=row.created_at,
        updated_at=row.updated_at,
        i_am_member=i_am_member,
    )


async def _caller_may_mutate_queue(
    company_id: str,
    user_id: str,
    queue_id: str,
    repo: OperatorRepository,
) -> bool:
    if await repo.is_user_member_of_queue(queue_id, user_id):
        return True
    if _company_operator_roles_normalized() & {"admin", "owner"}:
        return True
    return False


def _interrupt_handoff_texts(row: OperatorTasks) -> tuple[Optional[str], Optional[str]]:
    snap = row.interrupt_snapshot
    if snap is None or not isinstance(snap, dict):
        return None, None
    title: Optional[str] = None
    raw_t = snap.get("task_title")
    if raw_t is not None:
        s = str(raw_t).strip()
        if s:
            title = s
    preview: Optional[str] = None
    raw_q = snap.get("question")
    if raw_q is not None:
        q = str(raw_q).strip()
        if q:
            if len(q) > HANDOFF_PREVIEW_MAX_LEN:
                preview = q[: HANDOFF_PREVIEW_MAX_LEN - 1].rstrip() + "\u2026"
            else:
                preview = q
    return title, preview


def _flow_display_name(flow_cfg: Optional[FlowConfig], flow_id: str) -> str:
    if flow_cfg is None:
        return flow_id
    n = flow_cfg.name.strip()
    return n if n else flow_id


def _skill_display_name(flow_cfg: Optional[FlowConfig], skill_id: str) -> str:
    if flow_cfg is not None and flow_cfg.skills:
        sk = flow_cfg.skills.get(skill_id)
        if sk is not None:
            sn = sk.name.strip()
            return sn if sn else skill_id
    return skill_id


def _task_to_out(
    row: OperatorTasks,
    *,
    flow_cfg: Optional[FlowConfig] = None,
) -> OperatorTaskOut:
    ht, hp = _interrupt_handoff_texts(row)
    handoff_mode = parse_handoff_mode(row).value
    return OperatorTaskOut(
        id=row.id,
        company_id=row.company_id,
        queue_id=row.queue_id,
        status=row.status,
        session_id=row.session_id,
        end_user_id=row.end_user_id,
        flow_id=row.flow_id,
        skill_id=row.skill_id,
        flow_display_name=_flow_display_name(flow_cfg, row.flow_id),
        skill_display_name=_skill_display_name(flow_cfg, row.skill_id),
        handoff_title=ht,
        handoff_message_preview=hp,
        handoff_mode=handoff_mode,
        a2a_task_id=row.a2a_task_id,
        context_id=row.context_id,
        correlation_id=row.correlation_id,
        claimed_by_user_id=row.claimed_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _flow_config_map_for_tasks(
    container: FlowContainer,
    rows: List[OperatorTasks],
) -> dict[str, Optional[FlowConfig]]:
    flow_ids = list({r.flow_id for r in rows})
    if not flow_ids:
        return {}
    loaded = await asyncio.gather(
        *[container.flow_repository.get(fid) for fid in flow_ids]
    )
    return dict(zip(flow_ids, loaded, strict=True))


@router.post("/queues", response_model=OperatorQueueOut)
async def create_queue(
    body: OperatorQueueCreate,
    container: ContainerDep,
) -> OperatorQueueOut:
    _require_operator_queue_manage_role()
    company_id, user_id = _company_and_user()
    repo = container.operator_repository
    qid = await repo.create_queue(
        company_id=company_id,
        name=body.name.strip(),
        slug=body.slug.strip(),
        description=body.description,
    )
    await repo.add_member(qid, user_id, role="agent")
    row = await repo.get_queue_by_id(company_id, qid)
    if row is None:
        raise HTTPException(status_code=500, detail="Очередь создана, но не читается")
    return _queue_to_out(row, i_am_member=True)


@router.get("/queues", response_model=OffsetPage[OperatorQueueOut])
async def list_queues(
    container: ContainerDep,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> OffsetPage[OperatorQueueOut]:
    _require_operator_queue_manage_role()
    company_id, user_id = _company_and_user()
    repo = container.operator_repository
    my_queue_ids = set(await repo.list_queue_ids_for_user(company_id, user_id))
    rows = await repo.list_queues(company_id)
    items = [_queue_to_out(r, i_am_member=r.id in my_queue_ids) for r in rows]
    page = items[offset:offset + limit]
    return OffsetPage[OperatorQueueOut](items=page, total=len(items), limit=limit, offset=offset)


@router.patch("/queues/{queue_id}", response_model=OperatorQueueOut)
async def patch_queue(
    queue_id: str,
    body: OperatorQueuePatch,
    container: ContainerDep,
) -> OperatorQueueOut:
    company_id, user_id = _company_and_user()
    repo = container.operator_repository
    row = await repo.get_queue_by_id(company_id, queue_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Очередь не найдена")
    if not await _caller_may_mutate_queue(company_id, user_id, queue_id, repo):
        raise HTTPException(status_code=403, detail="Нет доступа к очереди")
    await repo.update_queue(
        company_id,
        queue_id,
        name=body.name,
        description=body.description,
    )
    updated = await repo.get_queue_by_id(company_id, queue_id)
    if updated is None:
        raise HTTPException(status_code=500, detail="Очередь не найдена после обновления")
    i_am = await repo.is_user_member_of_queue(queue_id, user_id)
    return _queue_to_out(updated, i_am_member=i_am)


@router.post("/queues/{queue_id}/members")
async def add_queue_member(
    queue_id: str,
    body: OperatorMemberAdd,
    container: ContainerDep,
) -> dict[str, str]:
    company_id, user_id = _company_and_user()
    repo = container.operator_repository
    row = await repo.get_queue_by_id(company_id, queue_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Очередь не найдена")
    if not await _caller_may_mutate_queue(company_id, user_id, queue_id, repo):
        raise HTTPException(status_code=403, detail="Нет доступа к очереди")
    mid = await repo.add_member(queue_id, body.user_id.strip(), role=body.role.strip())
    await publish_operator_tasks_refresh(container.redis_client, repo, queue_id)
    return {"member_id": mid}


@router.delete("/queues/{queue_id}/members/{member_user_id}")
async def remove_queue_member(
    queue_id: str,
    member_user_id: str,
    container: ContainerDep,
) -> None:
    company_id, user_id = _company_and_user()
    repo = container.operator_repository
    row = await repo.get_queue_by_id(company_id, queue_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Очередь не найдена")
    if not await _caller_may_mutate_queue(company_id, user_id, queue_id, repo):
        raise HTTPException(status_code=403, detail="Нет доступа к очереди")
    await repo.remove_member(queue_id, member_user_id)
    await publish_operator_tasks_refresh(container.redis_client, repo, queue_id)


@router.get("/tasks", response_model=OffsetPage[OperatorTaskOut])
async def list_operator_tasks(
    container: ContainerDep,
    queue_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> OffsetPage[OperatorTaskOut]:
    company_id, user_id = _company_and_user()
    repo = container.operator_repository
    allowed = await repo.list_queue_ids_for_user(company_id, user_id)
    if queue_id is not None:
        if not allowed or queue_id not in allowed:
            raise HTTPException(status_code=403, detail="Нет доступа к указанной очереди")
        rows, total = await repo.list_tasks(
            company_id,
            queue_id=queue_id,
            status=status,
            limit=limit,
            offset=offset,
        )
    else:
        if not allowed:
            return OffsetPage[OperatorTaskOut](items=[], total=0, limit=limit, offset=offset)
        rows, total = await repo.list_tasks(
            company_id,
            queue_ids=allowed,
            status=status,
            limit=limit,
            offset=offset,
        )
    rows_list = list(rows)
    flow_cfgs = await _flow_config_map_for_tasks(container, rows_list)
    return OffsetPage[OperatorTaskOut](
        items=[
            _task_to_out(r, flow_cfg=flow_cfgs.get(r.flow_id)) for r in rows_list
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/tasks/{task_id}")
async def get_operator_task(
    task_id: str,
    container: ContainerDep,
) -> dict[str, Any]:
    company_id, user_id = _company_and_user()
    repo = container.operator_repository
    task = await repo.get_task(company_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    if not await repo.is_user_member_of_queue(task.queue_id, user_id):
        raise HTTPException(status_code=403, detail="Нет доступа к задаче")
    dialog_messages: List[dict[str, Any]] = []
    saved = await container.state_manager.get_state(task.session_id)
    if saved is not None and saved.messages:
        for m in saved.messages:
            if hasattr(m, "model_dump"):
                dialog_messages.append(m.model_dump(mode="json"))
            elif isinstance(m, dict):
                dialog_messages.append(m)
    flow_cfg = await container.flow_repository.get(task.flow_id)
    return {
        "task": _task_to_out(task, flow_cfg=flow_cfg).model_dump(mode="json"),
        "interrupt_snapshot": task.interrupt_snapshot,
        "resolution_payload": task.resolution_payload,
        "dialog_log": task.dialog_log or [],
        "dialog_messages": dialog_messages,
    }


@router.patch("/tasks/{task_id}", response_model=OperatorTaskOut)
async def patch_operator_task(
    task_id: str,
    body: OperatorTaskPatch,
    container: ContainerDep,
) -> OperatorTaskOut:
    company_id, user_id = _company_and_user()
    repo = container.operator_repository
    task = await repo.get_task(company_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    if not await repo.is_user_member_of_queue(task.queue_id, user_id):
        raise HTTPException(status_code=403, detail="Нет доступа к задаче")
    allowed_status = {s.value for s in OperatorTaskStatus}
    if body.status not in allowed_status:
        raise HTTPException(status_code=400, detail="Неизвестный статус задачи")
    queue_id = task.queue_id
    await repo.update_task_fields(company_id, task_id, status=body.status)
    await publish_operator_tasks_refresh(container.redis_client, repo, queue_id)
    updated = await repo.get_task(company_id, task_id)
    if updated is None:
        raise HTTPException(status_code=500, detail="Задача не найдена после обновления")
    flow_cfg = await container.flow_repository.get(updated.flow_id)
    return _task_to_out(updated, flow_cfg=flow_cfg)


@router.post("/tasks/{task_id}/claim", response_model=OperatorTaskOut)
async def claim_operator_task(
    task_id: str,
    container: ContainerDep,
) -> OperatorTaskOut:
    company_id, user_id = _company_and_user()
    svc = container.operator_handoff_service
    try:
        await svc.claim_task(
            company_id=company_id, task_id=task_id, operator_user_id=user_id
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    updated = await container.operator_repository.get_task(company_id, task_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    flow_cfg = await container.flow_repository.get(updated.flow_id)
    return _task_to_out(updated, flow_cfg=flow_cfg)


@router.post("/tasks/{task_id}/messages")
async def post_operator_task_message(
    task_id: str,
    body: OperatorTaskMessageBody,
    container: ContainerDep,
) -> dict[str, str]:
    company_id, user_id = _company_and_user()
    svc = container.operator_handoff_service
    try:
        await svc.publish_operator_message_to_user_stream(
            company_id=company_id,
            task_id=task_id,
            operator_user_id=user_id,
            text=body.text,
            file_ids=body.file_ids,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"status": "sent"}


@router.post("/tasks/{task_id}/complete")
async def complete_operator_task(
    task_id: str,
    body: OperatorTaskCompleteBody,
    container: ContainerDep,
) -> dict[str, str]:
    company_id, user_id = _company_and_user()
    svc = container.operator_handoff_service
    try:
        await svc.complete_handoff(
            company_id=company_id,
            task_id=task_id,
            operator_user_id=user_id,
            resolution=body.resolution,
            file_ids=body.file_ids,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"status": "completed"}
