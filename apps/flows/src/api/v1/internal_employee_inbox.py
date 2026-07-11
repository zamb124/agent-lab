"""Единый internal inbox «платформа → flow-сотрудник».

Одна точка входа для входящей работы сотруднику-агенту: sync-меншены/DM и назначение
задач worktracker. Поверхности (sync, worktracker) не знают про flows-домен — они шлют
типизированный payload сюда, endpoint резолвит flow по employee-user, собирает
``context_id`` от источника и запускает flow через стандартный ``process_flow_task``
от имени сотрудника (SESSION JWT), сохраняя инициатора-отправителя для эскалаций.

Авторизация — signed internal headers (путь в whitelist-префиксе `/flows/api/v1/internal/`).
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import Field

from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.services.execution_identity import resolve_execution_context
from apps.flows.src.tasks.task_names import TASK_PROCESS_FLOW
from apps.flows_worker.broker_core import broker as flows_broker
from core.context.job_context import build_job_context
from core.identity.flow_employee import is_flow_employee, require_flow_employee_flow_id
from core.logging import get_logger
from core.models import StrictBaseModel
from core.tasks.kicker import kiq_task_name_with_context
from core.types import JsonObject

logger = get_logger(__name__)

router = APIRouter(tags=["internal-employee-inbox"])


class SyncMessageInbox(StrictBaseModel):
    """Входящее сообщение sync (mention или DM) сотруднику-агенту."""

    source: Literal["sync_message"] = "sync_message"
    company_id: str
    employee_user_id: str
    sender_user_id: str
    channel_id: str
    message_id: str
    text: str


class WorkItemAssignedInbox(StrictBaseModel):
    """Назначение задачи worktracker сотруднику-агенту."""

    source: Literal["work_item_assigned"] = "work_item_assigned"
    company_id: str
    employee_user_id: str
    sender_user_id: str
    work_item_id: str
    text: str
    branch_id: str = "default"


EmployeeInboxPayload = Annotated[
    SyncMessageInbox | WorkItemAssignedInbox,
    Field(discriminator="source"),
]


@router.post("/employee/inbox")
async def employee_inbox(container: ContainerDep, body: EmployeeInboxPayload) -> JsonObject:
    """Запускает flow-сотрудника на входящую работу от sync/worktracker."""
    employee_user = await container.user_repository.get(body.employee_user_id)
    if employee_user is None:
        raise ValueError(f"employee inbox: user {body.employee_user_id} not found")
    if not is_flow_employee(employee_user):
        return {"status": "ignored", "reason": "not_flow_employee"}
    flow_id = require_flow_employee_flow_id(employee_user)

    company = await container.company_repository.get(body.company_id)
    if company is None:
        raise ValueError(f"employee inbox: company {body.company_id} not found")

    sender = await container.user_repository.get(body.sender_user_id)
    if sender is None:
        raise ValueError(f"employee inbox: sender {body.sender_user_id} not found")

    flow_config = await container.flow_repository.get(flow_id)
    if flow_config is None:
        raise ValueError(f"employee inbox: flow {flow_id} not found")

    initiator_context = build_job_context(
        company=company,
        user=sender,
        host="",
        trace_id="",
        session_id="",
        channel="employee_inbox",
    )
    execution = await resolve_execution_context(
        as_flow_runtime_container(container),
        flow_config=flow_config,
        initiator_context=initiator_context,
    )

    if isinstance(body, SyncMessageInbox):
        context_id = f"sync:{body.channel_id}"
        metadata: JsonObject = {
            "employee_inbox_source": "sync_message",
            "channel_id": body.channel_id,
            "message_id": body.message_id,
        }
    else:
        context_id = f"work_item:{body.work_item_id}"
        metadata = {
            "employee_inbox_source": "work_item_assigned",
            "work_item_id": body.work_item_id,
        }

    branch_id = body.branch_id if isinstance(body, WorkItemAssignedInbox) else "default"
    session_id = f"{flow_id}:{context_id}"

    logger.info(
        "internal.employee_inbox.run",
        flow_id=flow_id,
        employee_user_id=body.employee_user_id,
        source=body.source,
        context_id=context_id,
    )
    _ = await kiq_task_name_with_context(
        TASK_PROCESS_FLOW,
        flows_broker,
        flow_id=flow_id,
        session_id=session_id,
        user_id=execution.context.user.user_id,
        initiator_user_id=execution.initiator_user_id,
        content=body.text,
        branch_id=branch_id,
        channel="a2a",
        task_id=context_id,
        context_id=context_id,
        metadata=metadata,
        is_resume=False,
        files=[],
        context_data=execution.context.to_dict(),
        trace_context=None,
        background_kind="employee_inbox",
    )
    return {"status": "enqueued", "flow_id": flow_id, "context_id": context_id}
