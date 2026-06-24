"""
Одноразовая миграция данных в ядро задач WorkItem (platform_worktracker).

Переносит:
  1. operator_queues / operator_queue_members (flows, platform_agents)
     → work_queues / work_queue_members (member = UserActor).
  2. operator_tasks → WorkItem(kind=operator_handoff) с flow_session-link и
     hooks (completed + comment); dialog_log → WorkItemComment(role).
  3. CRM entity_type=task (crm, platform_crm) → WorkItem(kind=crm_activity) с
     1:1 crm_entity-link; перенос attributes.status/assignees/due_date/priority.

Легаси-таблицы operator_* читаются сырым SQL: ORM-модели уже удалены, а сами
таблицы существуют до drop-миграции flows (запускать этот скрипт до неё).

Запуск:
    uv run python -m scripts.migrate_to_worktracker

Идемпотентность: повторный запуск пропускает уже перенесённые сущности
(operator — по correlation_id в hooks.binding; CRM — по детерминированному id).
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import get_settings
from core.files.file_attachments import minimal_file_refs_from_file_ids
from core.logging import get_logger
from core.types import JsonObject
from core.worktracker.db import WorktrackerDatabase
from core.worktracker.models import (
    CrmEntityLink,
    FlowSessionLink,
    QueueAssignment,
    SystemActor,
    UnassignedAssignment,
    UserActor,
    UsersAssignment,
    WorkItem,
    WorkItemComment,
    WorkItemCommentRole,
    WorkItemHook,
    WorkItemHookEvent,
    WorkItemKind,
    WorkItemPriority,
    WorkItemState,
    WorkQueue,
    WorkQueueMember,
)
from core.worktracker.repository import WorktrackerRepository

logger = get_logger(__name__)

_OPERATOR_STATE_MAP: dict[str, WorkItemState] = {
    "open": WorkItemState.OPEN,
    "claimed": WorkItemState.IN_PROGRESS,
    "user_dialog": WorkItemState.IN_PROGRESS,
    "awaiting_agent": WorkItemState.BLOCKED,
    "completed": WorkItemState.DONE,
    "cancelled": WorkItemState.CANCELLED,
}

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

_COMMENT_ROLE_MAP: dict[str, WorkItemCommentRole] = {
    "operator": WorkItemCommentRole.OPERATOR,
    "user": WorkItemCommentRole.USER,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _session_factory(url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(url, poolclass=None)
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def migrate_operator_queues(
    flows_sf: async_sessionmaker[AsyncSession],
    repo: WorktrackerRepository,
) -> dict[str, str]:
    """Переносит очереди. Возвращает map старый queue_id → новый work_queue_id."""
    queue_id_map: dict[str, str] = {}
    queue_company: dict[str, str] = {}
    async with flows_sf() as session:
        queue_rows = (
            await session.execute(
                text(
                    "SELECT id, company_id, name, slug, description, created_at, updated_at "
                    "FROM operator_queues"
                )
            )
        ).mappings().all()
        member_rows = (
            await session.execute(
                text("SELECT queue_id, user_id, role FROM operator_queue_members")
            )
        ).mappings().all()
    for queue in queue_rows:
        queue_company[queue["id"]] = queue["company_id"]
        existing = await repo.get_queue_by_slug(queue["company_id"], queue["slug"])
        if existing is not None:
            queue_id_map[queue["id"]] = existing.work_queue_id
            continue
        created = await repo.insert_queue(
            WorkQueue(
                work_queue_id=f"wq_{queue['id']}",
                company_id=queue["company_id"],
                name=queue["name"],
                work_queue_slug=queue["slug"],
                description=queue["description"],
                created_at=queue["created_at"] or _utcnow(),
                updated_at=queue["updated_at"] or _utcnow(),
            )
        )
        queue_id_map[queue["id"]] = created.work_queue_id
    for member in member_rows:
        new_queue_id = queue_id_map.get(member["queue_id"])
        company_id = queue_company.get(member["queue_id"])
        if new_queue_id is None or company_id is None:
            continue
        await repo.add_queue_member(
            WorkQueueMember(
                work_queue_id=new_queue_id,
                member=UserActor(user_id=member["user_id"]),
                role=member["role"],
            ),
            company_id,
        )
    logger.info("worktracker.migrate.queues", count=len(queue_id_map))
    return queue_id_map


async def migrate_operator_tasks(
    flows_sf: async_sessionmaker[AsyncSession],
    repo: WorktrackerRepository,
    queue_id_map: dict[str, str],
) -> int:
    async with flows_sf() as session:
        task_rows = (
            await session.execute(
                text(
                    "SELECT id, company_id, queue_id, status, session_id, end_user_id, "
                    "flow_id, branch_id, a2a_task_id, context_id, correlation_id, "
                    "interrupt_snapshot, claimed_by_user_id, dialog_log, "
                    "context_data_snapshot, created_at, updated_at FROM operator_tasks"
                )
            )
        ).mappings().all()
    migrated = 0
    for task in task_rows:
        correlation_id = task["correlation_id"]
        if correlation_id is not None:
            existing = await repo.find_work_item_by_correlation(task["company_id"], correlation_id)
            if existing is not None:
                continue
        state = _OPERATOR_STATE_MAP.get(task["status"], WorkItemState.OPEN)
        new_queue_id = queue_id_map.get(task["queue_id"], f"wq_{task['queue_id']}")
        snapshot = task["interrupt_snapshot"] if isinstance(task["interrupt_snapshot"], dict) else {}
        title = snapshot.get("task_title")
        title_str = title.strip() if isinstance(title, str) and title.strip() else f"Задача {task['id']}"
        binding: JsonObject = {
            "correlation_id": correlation_id or "",
            "session_id": task["session_id"],
            "flow_id": task["flow_id"],
            "branch_id": task["branch_id"],
            "a2a_task_id": task["a2a_task_id"],
            "context_id": task["context_id"],
            "end_user_id": task["end_user_id"],
            "handoff_mode": snapshot.get("handoff_mode", "single_reply"),
            "interrupt_snapshot": snapshot,
            "context_data_snapshot": task["context_data_snapshot"] or {},
        }
        now = _utcnow()
        work_item_id = f"wi_{task['id']}"
        item = WorkItem(
            work_item_id=work_item_id,
            company_id=task["company_id"],
            title=title_str,
            description="",
            kind=WorkItemKind.OPERATOR_HANDOFF,
            state=state,
            priority=WorkItemPriority.NORMAL,
            created_by=SystemActor(),
            assignment=QueueAssignment(
                work_queue_id=new_queue_id,
                claimed_by_user_id=task["claimed_by_user_id"],
            ),
            blocking=True,
            hooks=[
                WorkItemHook(
                    event=WorkItemHookEvent.COMPLETED,
                    service="flows",
                    path="/flows/api/v1/internal/work-items/completed",
                    binding=binding,
                ),
                WorkItemHook(
                    event=WorkItemHookEvent.COMMENT,
                    service="flows",
                    path="/flows/api/v1/internal/work-items/comment",
                    binding=binding,
                ),
            ],
            links=[
                FlowSessionLink(
                    session_id=task["session_id"],
                    a2a_task_id=task["a2a_task_id"],
                    context_id=task["context_id"],
                )
            ],
            created_at=task["created_at"] or now,
            updated_at=task["updated_at"] or now,
        )
        _ = await repo.insert_work_item(item)
        await _migrate_dialog_log(repo, work_item_id, task["company_id"], task["dialog_log"])
        migrated += 1
    logger.info("worktracker.migrate.operator_tasks", count=migrated)
    return migrated


async def _migrate_dialog_log(
    repo: WorktrackerRepository,
    work_item_id: str,
    company_id: str,
    dialog_log: object,
) -> None:
    if not isinstance(dialog_log, list):
        return
    entries: list[object] = list(dialog_log)
    for index, raw_entry in enumerate(entries):
        if not isinstance(raw_entry, dict):
            continue
        entry: dict[str, object] = {str(k): v for k, v in raw_entry.items()}
        role_value = entry.get("role")
        role = _COMMENT_ROLE_MAP.get(
            role_value if isinstance(role_value, str) else "", WorkItemCommentRole.SYSTEM
        )
        user_id = entry.get("user_id")
        author = UserActor(user_id=user_id) if isinstance(user_id, str) and user_id else SystemActor()
        text_value = entry.get("text")
        file_ids_value = entry.get("file_ids")
        file_ids = (
            [str(f) for f in file_ids_value] if isinstance(file_ids_value, list) else []
        )
        _ = await repo.append_comment(
            WorkItemComment(
                comment_id=f"wic_{work_item_id}_{index}",
                work_item_id=work_item_id,
                company_id=company_id,
                author=author,
                role=role,
                text=text_value if isinstance(text_value, str) else "",
                files=minimal_file_refs_from_file_ids(file_ids),
                created_at=_utcnow(),
            )
        )


async def migrate_crm_tasks(
    crm_sf: async_sessionmaker[AsyncSession],
    repo: WorktrackerRepository,
) -> int:
    # Колонки work-полей уже удалены из ORM-модели; читаем сырым SQL ДО drop-ревизии CRM.
    async with crm_sf() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT entity_id, company_id, namespace, name, attributes, "
                    "assignees, due_date FROM crm_entities WHERE entity_type = 'task'"
                )
            )
        ).mappings().all()
    migrated = 0
    for row in rows:
        entity_id = row["entity_id"]
        company_id = row["company_id"]
        work_item_id = f"wi_{entity_id}"
        if await repo.get_work_item(company_id, work_item_id) is not None:
            continue
        attributes = row["attributes"] if isinstance(row["attributes"], dict) else {}
        priority_raw = attributes.get("priority")
        priority = _PRIORITY_MAP.get(
            priority_raw if isinstance(priority_raw, str) else "normal", WorkItemPriority.NORMAL
        )
        status_raw = attributes.get("status")
        state = _STATUS_STATE_MAP.get(
            status_raw if isinstance(status_raw, str) else "", WorkItemState.OPEN
        )
        assignees_raw = row["assignees"]
        assignees = [str(a) for a in assignees_raw] if isinstance(assignees_raw, list) else []
        assignment = (
            UsersAssignment(user_ids=assignees) if assignees else UnassignedAssignment()
        )
        due_date = row["due_date"]
        if isinstance(due_date, datetime):
            due_at: datetime | None = due_date
        elif isinstance(due_date, date):
            due_at = datetime.combine(due_date, time.min, tzinfo=timezone.utc)
        else:
            due_at = None
        now = _utcnow()
        item = WorkItem(
            work_item_id=work_item_id,
            company_id=company_id,
            namespace=row["namespace"],
            title=row["name"] or f"Задача {entity_id}",
            description="",
            kind=WorkItemKind.CRM_ACTIVITY,
            state=state,
            priority=priority,
            due_date=due_at,
            created_by=SystemActor(),
            assignment=assignment,
            blocking=False,
            links=[CrmEntityLink(entity_id=entity_id)],
            created_at=now,
            updated_at=now,
        )
        _ = await repo.insert_work_item(item)
        migrated += 1
    logger.info("worktracker.migrate.crm_tasks", count=migrated)
    return migrated


async def main() -> None:
    settings = get_settings()
    if not settings.database.worktracker_url:
        raise ValueError("database.worktracker_url не задан")
    if not settings.database.flows_url:
        raise ValueError("database.flows_url не задан")
    if not settings.database.crm_url:
        raise ValueError("database.crm_url не задан")

    repo = WorktrackerRepository(db=WorktrackerDatabase(settings.database.worktracker_url))
    flows_sf = _session_factory(settings.database.flows_url)
    crm_sf = _session_factory(settings.database.crm_url)

    queue_id_map = await migrate_operator_queues(flows_sf, repo)
    _ = await migrate_operator_tasks(flows_sf, repo, queue_id_map)
    _ = await migrate_crm_tasks(crm_sf, repo)
    logger.info("worktracker.migrate.done")


if __name__ == "__main__":
    asyncio.run(main())
