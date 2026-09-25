"""Типы событий CRM в каталоге платформы: доменные (entity/relationship) и realtime-push для UI."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from apps.crm.models.api import EntityResponse
from apps.crm.models.crm_entity import CRMEntity
from apps.crm.models.task import CRMTask
from core.events import publish_domain_event, register_platform_event
from core.types import JsonObject

CRM_ENTITY_CREATED = "crm/entity/created"
CRM_ENTITY_UPDATED = "crm/entity/updated"
CRM_ENTITY_DELETED = "crm/entity/deleted"


class CrmEntityEventPayload(BaseModel):
    """Payload событий `crm/entity/*`."""

    entity_id: str
    entity_type: str
    entity_subtype: str | None
    namespace: str
    name: str
    status: str
    tags: list[str]
    actor_user_id: str


register_platform_event(
    CRM_ENTITY_CREATED,
    CrmEntityEventPayload,
    description="Создана сущность CRM (person/organization/task/note/...).",
)
register_platform_event(
    CRM_ENTITY_UPDATED,
    CrmEntityEventPayload,
    description="Обновлена сущность CRM.",
)
register_platform_event(
    CRM_ENTITY_DELETED,
    CrmEntityEventPayload,
    description="Удалена сущность CRM.",
)


async def publish_crm_entity_event(event_type: str, entity: CRMEntity) -> None:
    """Опубликовать доменное событие по CRM entity."""
    payload = CrmEntityEventPayload(
        entity_id=entity.entity_id,
        entity_type=entity.entity_type,
        entity_subtype=entity.entity_subtype,
        namespace=entity.namespace,
        name=entity.name,
        status=entity.status,
        tags=list(entity.tags),
        actor_user_id=entity.user_id,
    )
    await publish_domain_event(
        event_type,
        payload.model_dump(mode="json"),
        company_id=entity.company_id,
        actor_user_id=entity.user_id,
    )


CRM_NOTE_UPDATED = "crm/note/updated"
CRM_TASK_UPDATED = "crm/task/updated"
CRM_DAILY_SUMMARY_UPDATED = "crm/daily_summary/updated"
CRM_PERIOD_SUMMARY_UPDATED = "crm/period_summary/updated"


class CrmNoteUpdatedEventPayload(BaseModel):
    """Payload `crm/note/updated`."""

    company_id: str
    namespace: str
    note_id: str
    note_date: str | None = None
    action: Literal["created", "updated", "deleted"]
    note: EntityResponse | None = None
    markdown_format: JsonObject | None = None
    draft_repair: JsonObject | None = None


class CrmTaskUpdatedEventPayload(BaseModel):
    """Payload `crm/task/updated`."""

    task: CRMTask


class CrmDailySummaryUpdatedEventPayload(BaseModel):
    """Payload `crm/daily_summary/updated`."""

    company_id: str
    namespace: str
    date: str
    state: JsonObject = Field(default_factory=dict)


class CrmPeriodSummaryUpdatedEventPayload(BaseModel):
    """Payload `crm/period_summary/updated`."""

    company_id: str
    namespace: str
    date_from: str
    date_to: str
    state: JsonObject = Field(default_factory=dict)


register_platform_event(
    CRM_NOTE_UPDATED,
    CrmNoteUpdatedEventPayload,
    description="Заметка CRM создана/изменена/удалена (UI slice notes).",
)
register_platform_event(
    CRM_TASK_UPDATED,
    CrmTaskUpdatedEventPayload,
    description="Строка crm_tasks обновлена (UI slice tasks).",
)
register_platform_event(
    CRM_DAILY_SUMMARY_UPDATED,
    CrmDailySummaryUpdatedEventPayload,
    description="Пересчитана дневная сводка CRM.",
)
register_platform_event(
    CRM_PERIOD_SUMMARY_UPDATED,
    CrmPeriodSummaryUpdatedEventPayload,
    description="Пересчитана периодная сводка CRM.",
)
