"""Доменное UI-событие о строке crm_tasks на шине `platform:events`."""

from __future__ import annotations

from apps.crm.db.models import CRMTask
from apps.crm.db.repositories.task_repository import TaskRepository
from apps.crm.models.api import TaskResponse
from apps.crm.services.crm_realtime_events import CRM_TASK_UPDATED
from core.events import publish_event_to_user


async def broadcast_crm_task_updated_for_user(*, user_id: str, row: CRMTask) -> None:
    task_payload = TaskResponse.model_validate(row).model_dump(mode="json")
    await publish_event_to_user(
        user_id=user_id,
        type=CRM_TASK_UPDATED,
        payload={"task": task_payload},
    )


async def publish_crm_task_snapshot_for_user(
    *,
    user_id: str,
    repo: TaskRepository,
    task_id: str,
    company_id: str,
) -> None:
    row = await repo.get_for_worker(task_id, company_id)
    if row is None:
        raise ValueError(f"CRM task not found: {task_id}")
    await broadcast_crm_task_updated_for_user(user_id=user_id, row=row)
