"""
Realtime-события ядра задач (server -> client) через шину `platform:events`.

Push-события зеркал REST не имеют (см. `architecture.mdc`). Доменные slice UI
обновляются по этим типам; durable-потребители шины (триггеры flows) получают
те же события at-least-once.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from core.events import (
    publish_domain_event,
    publish_event_to_company,
    publish_event_to_users,
    register_platform_event,
)
from core.types import JsonObject
from core.worktracker.models import WorkItem, WorkItemComment

WORK_ITEM_CREATED = "worktracker/work_item/created"
WORK_ITEM_UPDATED = "worktracker/work_item/updated"
WORK_ITEM_MOVED = "worktracker/work_item/moved"
WORK_ITEM_COMPLETED = "worktracker/work_item/completed"
WORK_ITEM_COMMENT_CREATED = "worktracker/work_item/comment_created"
WORK_ITEM_ASSIGNED = "worktracker/work_item/assigned"

WorkItemEventType = Literal[
    "worktracker/work_item/created",
    "worktracker/work_item/updated",
    "worktracker/work_item/moved",
    "worktracker/work_item/completed",
    "worktracker/work_item/comment_created",
]


class WorkItemEventPayload(BaseModel):
    """Payload `worktracker/work_item/created|updated|moved|completed`."""

    work_item: WorkItem


class WorkItemAssignedEventPayload(BaseModel):
    """Payload `worktracker/work_item/assigned` (чисто доменное, delivery=None)."""

    work_item: WorkItem
    assigned_by_user_id: str


class WorkItemCommentEventPayload(BaseModel):
    """Payload `worktracker/work_item/comment_created`."""

    work_item_id: str
    comment: WorkItemComment


register_platform_event(
    WORK_ITEM_CREATED,
    WorkItemEventPayload,
    description="Создана задача WorkItem.",
)
register_platform_event(
    WORK_ITEM_UPDATED,
    WorkItemEventPayload,
    description="Задача WorkItem изменена (поля/assignment/claim).",
)
register_platform_event(
    WORK_ITEM_MOVED,
    WorkItemEventPayload,
    description="Задача WorkItem перемещена по доске / сменила state.",
)
register_platform_event(
    WORK_ITEM_COMPLETED,
    WorkItemEventPayload,
    description="Задача WorkItem завершена (done/cancelled/failed).",
)
register_platform_event(
    WORK_ITEM_ASSIGNED,
    WorkItemAssignedEventPayload,
    description="Задаче WorkItem назначен исполнитель (create/reassign).",
)
register_platform_event(
    WORK_ITEM_COMMENT_CREATED,
    WorkItemCommentEventPayload,
    description="К задаче WorkItem добавлен комментарий.",
)


async def publish_work_item_assigned(item: WorkItem, *, assigned_by_user_id: str) -> None:
    """Доменное событие о назначении исполнителя (без UI-доставки)."""
    payload = WorkItemAssignedEventPayload(
        work_item=item,
        assigned_by_user_id=assigned_by_user_id,
    )
    await publish_domain_event(
        WORK_ITEM_ASSIGNED,
        payload.model_dump(mode="json"),
        company_id=item.company_id,
        actor_user_id=assigned_by_user_id,
    )


class WorkItemRealtimeEvent(BaseModel):
    """Доменное событие WorkItem для рассылки через шину `platform:events`."""

    type: WorkItemEventType
    payload: JsonObject = Field(description="Сериализованный WorkItem или дельта.")
    company_id: str = Field(description="Компания-получатель (изоляция между тенантами).")
    recipient_user_ids: list[str] | None = Field(
        default=None,
        description="None — broadcast компании; иначе адресная отправка перечисленным user_id.",
    )


async def publish_work_item_events(events: list[WorkItemRealtimeEvent]) -> None:
    for event in events:
        if event.recipient_user_ids is None:
            await publish_event_to_company(
                company_id=event.company_id,
                type=event.type,
                payload=event.payload,
            )
        else:
            await publish_event_to_users(
                event.recipient_user_ids,
                event.type,
                event.payload,
                company_id=event.company_id,
            )
