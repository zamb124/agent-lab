"""
Доменное UI-событие о строке crm_tasks.

Публикует ``crm/task/updated`` в ``platform:ui_events`` для slice ``crm/tasks``
на фронте (без поллинга). Параллельно воркеры по-прежнему могут вызывать
``notify_user`` с ``CRM_TASK_UPDATED`` для notification-center.
"""

from __future__ import annotations

from apps.crm.db.models import CRMTask
from apps.crm.db.repositories.task_repository import TaskRepository
from apps.crm.models.api import TaskResponse
from core.ui_events import publish_ui_event_to_user


async def broadcast_crm_task_updated_for_user(*, user_id: str, row: CRMTask) -> None:
    task_payload = TaskResponse.model_validate(row).model_dump(mode="json")
    await publish_ui_event_to_user(
        user_id=user_id,
        type="crm/task/updated",
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
