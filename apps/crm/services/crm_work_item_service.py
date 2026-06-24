"""
Парный WorkItem для CRM-задачи.

CRM-узел `entity_type=task` остаётся графовой сущностью (имя/описание/атрибуты/связи)
для AI и эмбеддинга, а вся work-семантика (state/priority/due_date/assignee) живёт в
платформенном ядре `WorkItem(kind=crm_activity)` со связью 1:1 через `CrmEntityLink`.

Сервис — тонкий CRM-адаптер над `core.worktracker.WorkItemService`: маппинг
CRM-сидов в WorkItem и синхронизация 1:1.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from pydantic import BaseModel, Field

from core.worktracker.models import (
    CrmEntityLink,
    SystemActor,
    UnassignedAssignment,
    UsersAssignment,
    WorkActor,
    WorkItem,
    WorkItemAssignment,
    WorkItemKind,
    WorkItemPriority,
    WorkItemState,
)
from core.worktracker.service import WorkItemService

_PRIORITY_MAP: dict[str, WorkItemPriority] = {
    "low": WorkItemPriority.LOW,
    "normal": WorkItemPriority.NORMAL,
    "medium": WorkItemPriority.NORMAL,
    "high": WorkItemPriority.HIGH,
    "urgent": WorkItemPriority.URGENT,
}

_STATUS_STATE_MAP: dict[str, WorkItemState] = {
    "todo": WorkItemState.OPEN,
    "open": WorkItemState.OPEN,
    "backlog": WorkItemState.OPEN,
    "in_progress": WorkItemState.IN_PROGRESS,
    "doing": WorkItemState.IN_PROGRESS,
    "review": WorkItemState.IN_PROGRESS,
    "blocked": WorkItemState.BLOCKED,
    "done": WorkItemState.DONE,
    "completed": WorkItemState.DONE,
    "cancelled": WorkItemState.CANCELLED,
}


class CrmTaskWorkSeed(BaseModel):
    """Work-намерение CRM-задачи для синхронизации в парный WorkItem."""

    priority: str | None = None
    due_date: date | None = None
    assignees: list[str] = Field(default_factory=list)
    board_status: str | None = None


class CrmWorkItemService:
    """Синхронизация парного `WorkItem(crm_activity)` для CRM-узла задачи."""

    def __init__(self, work_item_service: WorkItemService) -> None:
        self._wi: WorkItemService = work_item_service

    @staticmethod
    def _priority(value: str | None) -> WorkItemPriority:
        if value is None:
            return WorkItemPriority.NORMAL
        return _PRIORITY_MAP.get(value.strip().lower(), WorkItemPriority.NORMAL)

    @staticmethod
    def _state(board_status: str | None) -> WorkItemState:
        if board_status is None:
            return WorkItemState.OPEN
        return _STATUS_STATE_MAP.get(board_status.strip().lower(), WorkItemState.OPEN)

    @staticmethod
    def _due(value: date | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return datetime.combine(value, time.min, tzinfo=timezone.utc)

    @staticmethod
    def _assignment(assignees: list[str]) -> WorkItemAssignment:
        cleaned = [a for a in assignees if a]
        if cleaned:
            return UsersAssignment(user_ids=cleaned)
        return UnassignedAssignment()

    async def sync_for_task(
        self,
        *,
        company_id: str,
        entity_id: str,
        namespace: str,
        title: str,
        description: str = "",
        seed: CrmTaskWorkSeed,
        created_by: WorkActor | None = None,
    ) -> WorkItem:
        """Создать или обновить парный WorkItem CRM-задачи (1:1 по entity_id)."""
        existing = await self._wi.find_by_crm_entity(company_id, entity_id)
        target_state = self._state(seed.board_status)
        if existing is None:
            created = await self._wi.create(
                company_id=company_id,
                title=title or f"Задача {entity_id}",
                created_by=created_by or SystemActor(),
                description=description,
                kind=WorkItemKind.CRM_ACTIVITY,
                namespace=namespace,
                priority=self._priority(seed.priority),
                due_date=self._due(seed.due_date),
                assignment=self._assignment(seed.assignees),
                links=[CrmEntityLink(entity_id=entity_id)],
            )
            if target_state is not WorkItemState.OPEN:
                moved = await self._wi.move(
                    company_id=company_id,
                    work_item_id=created.work_item_id,
                    state=target_state,
                )
                return moved
            return created
        _ = await self._wi.update(
            company_id=company_id,
            work_item_id=existing.work_item_id,
            title=title or existing.title,
            description=description,
            priority=self._priority(seed.priority),
            due_date=self._due(seed.due_date),
        )
        if existing.state not in {
            WorkItemState.DONE,
            WorkItemState.CANCELLED,
            WorkItemState.FAILED,
        }:
            _ = await self._wi.reassign(
                company_id=company_id,
                work_item_id=existing.work_item_id,
                assignment=self._assignment(seed.assignees),
            )
            if target_state is not existing.state:
                _ = await self._wi.move(
                    company_id=company_id,
                    work_item_id=existing.work_item_id,
                    state=target_state,
                )
        refreshed = await self._wi.get(company_id, existing.work_item_id)
        return refreshed

    async def delete_for_task(self, *, company_id: str, entity_id: str) -> None:
        existing = await self._wi.find_by_crm_entity(company_id, entity_id)
        if existing is not None:
            _ = await self._wi.delete(
                company_id=company_id, work_item_id=existing.work_item_id
            )

    async def get_for_task(self, *, company_id: str, entity_id: str) -> WorkItem | None:
        return await self._wi.find_by_crm_entity(company_id, entity_id)

    async def map_work_item_ids_by_entities(
        self, *, company_id: str, entity_ids: list[str]
    ) -> dict[str, str]:
        return await self._wi.map_work_item_ids_by_crm_entities(company_id, entity_ids)


__all__ = ["CrmWorkItemService", "CrmTaskWorkSeed"]
