"""
Внутренние endpoints flows для хуков жизненного цикла WorkItem.

Сервис worktracker дёргает их через ServiceClient на событиях задачи:
- `completed` → возобновление durable workflow (HITL resume);
- `assigned`  → агентский инбокс: запуск flow при назначении задачи на агента;
- `comment`   → takeover-бридж: стрим комментария оператора конечному пользователю.

`binding` — flows-owned данные, положенные при регистрации задачи.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.durable_execution import create_initial_state
from apps.flows.src.streaming.emitter import Emitter
from apps.flows.src.tasks.task_names import TASK_PROCESS_FLOW
from apps.flows_worker.broker_core import broker as flows_broker
from core.context import require_context
from core.files.file_attachments import file_ref_ids, parse_file_refs
from core.files.file_ref import FileRef
from core.logging import get_logger
from core.models import StrictBaseModel
from core.tasks.kicker import kiq_task_name_with_context
from core.types import JsonObject
from core.worktracker.models import WorkItemResolution

logger = get_logger(__name__)

router = APIRouter(tags=["internal-work-items"])


class WorkItemCompletedBody(StrictBaseModel):
    event: str = "completed"
    work_item_id: str
    company_id: str
    state: str
    resolution_text: str = ""
    resolution_files: list[FileRef] = Field(default_factory=list)
    binding: JsonObject


class WorkItemAssignedBody(StrictBaseModel):
    event: str = "assigned"
    work_item_id: str
    company_id: str
    assignment: JsonObject
    binding: JsonObject = {}


class WorkItemCommentBody(StrictBaseModel):
    event: str = "comment"
    work_item_id: str
    company_id: str
    comment: JsonObject
    binding: JsonObject


@router.post("/work-items/completed")
async def work_item_completed(container: ContainerDep, body: WorkItemCompletedBody) -> JsonObject:
    """Возобновляет flow по завершённой operator-handoff задаче WorkItem."""
    logger.info("internal.work_item.completed", work_item_id=body.work_item_id, state=body.state)
    resolution = WorkItemResolution(
        text=body.resolution_text,
        files=body.resolution_files,
    )
    await container.hitl_work_item_service.resume_from_completion(
        company_id=body.company_id,
        work_item_id=body.work_item_id,
        binding=body.binding,
        resolution=resolution,
    )
    return {"status": "resumed", "work_item_id": body.work_item_id}


@router.post("/work-items/assigned")
async def work_item_assigned(container: ContainerDep, body: WorkItemAssignedBody) -> JsonObject:
    """Агентский инбокс: запускает flow, если задача назначена на агента."""
    if body.assignment.get("assignee_kind") != "agent":
        return {"status": "ignored", "work_item_id": body.work_item_id}
    flow_id_raw = body.assignment.get("flow_id")
    if not isinstance(flow_id_raw, str) or not flow_id_raw:
        return {"status": "ignored", "work_item_id": body.work_item_id}

    work_item = await container.work_item_service.get(body.company_id, body.work_item_id)
    branch_raw = body.assignment.get("branch_id")
    branch_id = branch_raw if isinstance(branch_raw, str) and branch_raw else "default"
    ctx = require_context()
    context_id = f"wi-{body.work_item_id}"
    content = f"[Назначена задача] {work_item.title}\n\n{work_item.description}".strip()

    logger.info(
        "internal.work_item.assigned.agent_run",
        work_item_id=body.work_item_id,
        flow_id=flow_id_raw,
    )
    _ = await kiq_task_name_with_context(
        TASK_PROCESS_FLOW,
        flows_broker,
        flow_id=flow_id_raw,
        session_id=f"{flow_id_raw}:{context_id}",
        user_id=ctx.user.user_id,
        content=content,
        branch_id=branch_id,
        channel="a2a",
        task_id=context_id,
        context_id=context_id,
        metadata={"work_item_id": body.work_item_id},
        is_resume=False,
        files=[],
        context_data=ctx.to_dict(),
        trace_context=None,
        background_kind="work_item_assigned",
    )
    return {"status": "agent_run_enqueued", "work_item_id": body.work_item_id}


@router.post("/work-items/comment")
async def work_item_comment(container: ContainerDep, body: WorkItemCommentBody) -> JsonObject:
    """Takeover-бридж: стрим комментария оператора конечному пользователю через Emitter."""
    if body.comment.get("role") != "operator":
        return {"status": "ignored", "work_item_id": body.work_item_id}
    text_raw = body.comment.get("text")
    text = text_raw.strip() if isinstance(text_raw, str) else ""
    file_ids = file_ref_ids(parse_file_refs(body.comment.get("files")))
    if not file_ids:
        legacy_ids = body.comment.get("file_ids")
        if isinstance(legacy_ids, list):
            file_ids = [str(item) for item in legacy_ids]
    if not text and not file_ids:
        return {"status": "empty", "work_item_id": body.work_item_id}

    session_id = _require_binding_str(body.binding, "session_id")
    end_user_id = _require_binding_str(body.binding, "end_user_id")
    a2a_task_id_raw = body.binding.get("a2a_task_id")
    a2a_task_id = a2a_task_id_raw if isinstance(a2a_task_id_raw, str) and a2a_task_id_raw else ""
    context_id_raw = body.binding.get("context_id")
    context_id = (
        context_id_raw
        if isinstance(context_id_raw, str) and context_id_raw
        else session_id.split(":", 1)[-1]
    )
    branch_raw = body.binding.get("branch_id")
    branch_id = branch_raw if isinstance(branch_raw, str) and branch_raw else "default"

    exec_state = create_initial_state(
        task_id=a2a_task_id,
        context_id=context_id,
        user_id=end_user_id,
        session_id=session_id,
        branch_id=branch_id,
    )
    emitter = Emitter(container.redis_client, exec_state)
    if text:
        await emitter.emit_text(text, append=True, last_chunk=False, artifact_name="operator_reply")
    if file_ids:
        await emitter.emit_file_artifact(file_ids)
    return {"status": "streamed", "work_item_id": body.work_item_id}


def _require_binding_str(binding: JsonObject, key: str) -> str:
    value = binding.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"binding.{key} обязателен для takeover stream")
    return value
