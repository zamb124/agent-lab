"""Каталог realtime push-событий CRM на шине `platform:events`.

Доменные `crm/entity/*` — в `crm_entity_events.py`. Здесь — типы для
slice notes/tasks/summaries (одна запись стрима, `delivery.user_ids`).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from apps.crm.models.api import EntityResponse, TaskResponse
from core.events import register_platform_event
from core.types import JsonObject

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

    task: TaskResponse


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
