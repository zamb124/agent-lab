"""Доменное UI-событие о строке crm_tasks на шине `platform:events`."""

from __future__ import annotations

from apps.crm.events import CRM_TASK_UPDATED
from apps.crm.models.task import CRMTask
from core.events import publish_event_to_user


async def broadcast_crm_task_updated_for_user(*, user_id: str, row: CRMTask) -> None:
    await publish_event_to_user(
        user_id=user_id,
        type=CRM_TASK_UPDATED,
        payload={"task": row.model_dump(mode="json")},
    )


async def publish_crm_task_snapshot_for_user(
    *,
    user_id: str,
    task_id: str,
    company_id: str,
) -> None:
    row = await CRMTask.by_company_and_task_id(company_id, task_id)
    if row is None:
        raise ValueError(f"CRM task not found: {task_id}")
    await broadcast_crm_task_updated_for_user(user_id=user_id, row=row)
