"""
Внутренние endpoints flows для хуков жизненного цикла WorkItem.

Сервис worktracker дёргает их через ServiceClient на событиях задачи:
- `completed` → возобновление durable workflow (HITL resume);
- `assigned`  → агентский инбокс: запуск flow при назначении задачи на агента.

Диалог оператора/пользователя в HITL идёт через durable append в
`ExecutionState.messages` (см. `hitl_conversation_service`), а не через хук
`comment`. `WorkItemComment` — только внутренние заметки оператора.

`binding` — flows-owned данные, положенные при регистрации задачи.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.tasks.task_names import TASK_PROCESS_FLOW
from apps.flows_worker.broker_core import broker as flows_broker
from core.context import require_context
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
    resolution_file_ids: list[str] = Field(default_factory=list)
    binding: JsonObject


class WorkItemAssignedBody(StrictBaseModel):
    event: str = "assigned"
    work_item_id: str
    company_id: str
    assignment: JsonObject
    binding: JsonObject = {}


@router.post("/work-items/completed")
async def work_item_completed(container: ContainerDep, body: WorkItemCompletedBody) -> JsonObject:
    """Возобновляет flow по завершённой operator-handoff задаче WorkItem."""
    logger.info("internal.work_item.completed", work_item_id=body.work_item_id, state=body.state)
    resolution = WorkItemResolution(
        text=body.resolution_text,
        files=body.resolution_files,
    )
    await container.hitl_work_item_service.resume_from_completion(
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
