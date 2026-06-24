"""
Realtime-события ядра задач (server -> client) через `platform:ui_events`.

Push-события зеркал REST не имеют (см. `architecture.mdc`). Доменные slice UI
обновляются по этим типам.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from core.types import JsonObject
from core.ui_events.dispatcher import publish_ui_event_to_company, publish_ui_event_to_user

WORK_ITEM_CREATED = "worktracker/work_item/created"
WORK_ITEM_UPDATED = "worktracker/work_item/updated"
WORK_ITEM_MOVED = "worktracker/work_item/moved"
WORK_ITEM_COMPLETED = "worktracker/work_item/completed"
WORK_ITEM_COMMENT_CREATED = "worktracker/work_item/comment_created"

WorkItemEventType = Literal[
    "worktracker/work_item/created",
    "worktracker/work_item/updated",
    "worktracker/work_item/moved",
    "worktracker/work_item/completed",
    "worktracker/work_item/comment_created",
]


class WorkItemRealtimeEvent(BaseModel):
    """Доменное событие WorkItem для рассылки через `platform:ui_events`."""

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
            await publish_ui_event_to_company(
                company_id=event.company_id,
                type=event.type,
                payload=event.payload,
            )
        else:
            for user_id in event.recipient_user_ids:
                await publish_ui_event_to_user(
                    user_id=user_id,
                    type=event.type,
                    payload=event.payload,
                )
