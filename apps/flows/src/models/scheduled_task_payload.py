"""Payload контракт flow-задачи, исполняемой платформенным scheduler."""

from pydantic import Field

from core.models import StrictBaseModel
from core.scheduler.models import ContentType
from core.types import JsonObject


class FlowScheduledTaskPayload(StrictBaseModel):
    """TaskIQ kwargs для apps.flows.src.tasks.scheduled_tasks.execute_scheduled_task."""

    flow_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    content_type: ContentType
    content: str = Field(..., min_length=1)
    tool_args: JsonObject | None = None
    description: str | None = None
    schedule_task_id: str | None = None
    company_id: str | None = None


__all__ = ["FlowScheduledTaskPayload"]
