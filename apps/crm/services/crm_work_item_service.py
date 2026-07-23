"""
Парный WorkItem для CRM-задачи.

CRM-узел `entity_type=task` остаётся графовой сущностью (имя/описание/атрибуты/связи)
для AI и эмбеддинга, а вся work-семантика (state/priority/due_date/assignee) живёт в
платформенном ядре `WorkItem(kind=crm_activity)` со связью 1:1 через `CrmEntityLink`.

Сервис — тонкий CRM-адаптер над `core.worktracker.WorkItemService`: маппинг
CRM-сидов в WorkItem и синхронизация 1:1.

Partial update: поля seed применяются только если явно переданы
(`model_fields_set`). Rename CRM-узла не сбрасывает priority/assignees/state.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

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
    build_generic_board_columns,
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

_TERMINAL_STATES = frozenset(
    {
        WorkItemState.DONE,
        WorkItemState.CANCELLED,
        WorkItemState.FAILED,
    }
)


class CrmTaskWorkSeed(BaseModel):
    """Work-намерение CRM-задачи для синхронизации в парный WorkItem.

    Поля без явной передачи в конструкторе не меняют существующий WorkItem
    (см. ``model_fields_set`` в ``sync_for_task``).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    priority: str | None = None
    due_date: date | None = None
    assignees: list[str] | None = None
    board_status: str | None = None


class CrmWorkItemService:
    """Синхронизация парного `WorkItem(crm_activity)` для CRM-узла задачи."""

    def __init__(self, work_item_service: WorkItemService) -> None:
        self._wi: WorkItemService = work_item_service

    @staticmethod
    def board_key_for_subtype(entity_subtype: str | None) -> str:
        if entity_subtype is None:
            return "task"
        cleaned = entity_subtype.strip()
        if not cleaned:
            return "task"
        return f"task:{cleaned}"

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
    def _assignment(assignees: list[str] | None) -> WorkItemAssignment:
        if assignees is None:
            return UnassignedAssignment()
        cleaned = [a for a in assignees if a]
        if cleaned:
            return UsersAssignment(user_ids=cleaned)
        return UnassignedAssignment()

    async def _resolve_task_board(
        self,
        *,
        company_id: str,
        namespace: str,
        entity_subtype: str | None,
    ):
        board_key = self.board_key_for_subtype(entity_subtype)
        default_name = "Tasks" if board_key == "task" else f"Tasks ({entity_subtype})"
        return await self._wi.resolve_board_for(
            company_id=company_id,
            board_key=board_key,
            default_name=default_name,
            default_columns=build_generic_board_columns(),
            namespace=namespace,
        )

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
        entity_subtype: str | None = None,
    ) -> WorkItem:
        """Создать или обновить парный WorkItem CRM-задачи (1:1 по entity_id)."""
        existing = await self._wi.find_by_crm_entity(company_id, entity_id)
        fields_set = seed.model_fields_set

        if existing is None:
            board = await self._resolve_task_board(
                company_id=company_id,
                namespace=namespace,
                entity_subtype=entity_subtype,
            )
            priority = (
                self._priority(seed.priority)
                if "priority" in fields_set
                else WorkItemPriority.NORMAL
            )
            due_date = self._due(seed.due_date) if "due_date" in fields_set else None
            assignment = (
                self._assignment(seed.assignees)
                if "assignees" in fields_set
                else UnassignedAssignment()
            )
            target_state = (
                self._state(seed.board_status)
                if "board_status" in fields_set
                else WorkItemState.OPEN
            )
            created = await self._wi.create(
                company_id=company_id,
                title=title or f"Задача {entity_id}",
                created_by=created_by or SystemActor(),
                description=description,
                kind=WorkItemKind.CRM_ACTIVITY,
                namespace=namespace,
                board_id=board.board_id,
                priority=priority,
                due_date=due_date,
                assignment=assignment,
                links=[CrmEntityLink(entity_id=entity_id)],
            )
            if target_state is not WorkItemState.OPEN:
                return await self._wi.move(
                    company_id=company_id,
                    work_item_id=created.work_item_id,
                    state=target_state,
                )
            return created

        update_priority = (
            self._priority(seed.priority) if "priority" in fields_set else None
        )
        update_due = self._due(seed.due_date) if "due_date" in fields_set else None
        _ = await self._wi.update(
            company_id=company_id,
            work_item_id=existing.work_item_id,
            title=title or existing.title,
            description=description,
            priority=update_priority,
            due_date=update_due,
        )
        if existing.state not in _TERMINAL_STATES:
            if "assignees" in fields_set:
                _ = await self._wi.reassign(
                    company_id=company_id,
                    work_item_id=existing.work_item_id,
                    assignment=self._assignment(seed.assignees),
                )
            if "board_status" in fields_set:
                target_state = self._state(seed.board_status)
                if target_state is not existing.state:
                    _ = await self._wi.move(
                        company_id=company_id,
                        work_item_id=existing.work_item_id,
                        state=target_state,
                    )
        return await self._wi.get(company_id, existing.work_item_id)

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

    async def list_crm_activity_work_items(
        self,
        *,
        company_id: str,
        namespace: str | None = None,
        state: WorkItemState | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[WorkItem]:
        return await self._wi.list(
            company_id,
            namespace=namespace,
            kind=WorkItemKind.CRM_ACTIVITY,
            state=state,
            limit=limit,
            offset=offset,
        )


__all__ = ["CrmWorkItemService", "CrmTaskWorkSeed"]
