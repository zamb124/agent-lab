"""CRM activity-tasks: атомарная пара CRMEntity(task) + WorkItem(crm_activity)."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.crm.di import Di
from apps.crm.models.api import ActivityTaskCreateRequest, ActivityTaskResponse
from apps.crm.realtime.operations import (
    CrmActivityTasksListPayload,
    op_activity_tasks_create,
    op_activity_tasks_list,
)
from core.context import require_context
from core.pagination import OffsetPage
from core.worktracker.models import WorkItem, WorkItemState

router = APIRouter(prefix="/activity-tasks", tags=["activity-tasks"])


@router.post("", response_model=ActivityTaskResponse)
async def create_activity_task(
    body: ActivityTaskCreateRequest,
    di: Di,
) -> ActivityTaskResponse:
    return await op_activity_tasks_create(
        body, user=require_context().user, di=di
    )


@router.get("", response_model=OffsetPage[WorkItem])
async def list_activity_tasks(
    di: Di,
    namespace: str | None = None,
    state: WorkItemState | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[WorkItem]:
    return await op_activity_tasks_list(
        CrmActivityTasksListPayload(
            namespace=namespace,
            state=state,
            limit=limit,
            offset=offset,
        ),
        user=require_context().user,
        di=di,
    )
