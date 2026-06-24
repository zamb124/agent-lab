"""
Репозиторий ядра задач: CRUD WorkItem, очередей, досок и комментариев.

Конвертация domain <-> row строгая: union-поля валидируются через TypeAdapter,
никаких «мягких» дефолтов.
"""

from __future__ import annotations

from typing import cast

from pydantic import TypeAdapter
from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.sql import Select

from core.db.utils import get_rowcount
from core.files.file_attachments import minimal_file_refs_from_file_ids, parse_file_refs
from core.files.file_ref import FileRef
from core.types import JsonArray, JsonObject, require_json_object
from core.variables.models import VariableMap, normalize_variables_map
from core.worktracker.db import WorktrackerDatabase
from core.worktracker.db_models import (
    BoardRow,
    WorkItemCommentRow,
    WorkItemRow,
    WorkQueueMemberRow,
    WorkQueueRow,
)
from core.worktracker.models import (
    TERMINAL_WORK_ITEM_STATES,
    ActorKind,
    AgentActor,
    AssigneeKind,
    Board,
    BoardColumn,
    UserActor,
    WorkActor,
    WorkItem,
    WorkItemAssignment,
    WorkItemComment,
    WorkItemCommentRole,
    WorkItemHook,
    WorkItemKind,
    WorkItemLink,
    WorkItemPriority,
    WorkItemResolution,
    WorkItemState,
    WorkQueue,
    WorkQueueMember,
)

_ACTOR_ADAPTER: TypeAdapter[WorkActor] = TypeAdapter(WorkActor)
_ASSIGNMENT_ADAPTER: TypeAdapter[WorkItemAssignment] = TypeAdapter(WorkItemAssignment)
_LINKS_ADAPTER: TypeAdapter[list[WorkItemLink]] = TypeAdapter(list[WorkItemLink])
_HOOKS_ADAPTER: TypeAdapter[list[WorkItemHook]] = TypeAdapter(list[WorkItemHook])


def _actor_to_json(actor: WorkActor) -> JsonObject:
    return require_json_object(actor.model_dump(mode="json"), "WorkActor")


def _actor_from_json(raw: JsonObject) -> WorkActor:
    return _ACTOR_ADAPTER.validate_python(raw)


def _member_kind_ref(actor: WorkActor) -> tuple[str, str]:
    if isinstance(actor, UserActor):
        return ("user", actor.user_id)
    if isinstance(actor, AgentActor):
        return ("agent", actor.flow_id)
    raise ValueError("Участник очереди должен быть пользователем или агентом")


def _member_actor(member_kind: str, member_ref: str) -> WorkActor:
    if member_kind == "user":
        return UserActor(user_id=member_ref)
    if member_kind == "agent":
        return AgentActor(flow_id=member_ref)
    raise ValueError(f"Неизвестный member_kind {member_kind!r}")


def _assignment_text(key: str) -> ColumnElement[str]:
    """Типизированное извлечение скалярного поля из JSONB `assignment`."""
    return cast(
        ColumnElement[str],
        func.jsonb_extract_path_text(WorkItemRow.assignment, key),
    )


def _apply_work_item_filters(
    stmt: Select[tuple[WorkItemRow]],
    *,
    board_id: str | None,
    namespace: str | None,
    kind: WorkItemKind | None,
    state: WorkItemState | None,
    work_queue_id: str | None,
    assignee_user_id: str | None,
    assignee_flow_id: str | None,
    exclude_terminal: bool,
    queue_unclaimed_only: bool,
) -> Select[tuple[WorkItemRow]]:
    if board_id is not None:
        stmt = stmt.where(WorkItemRow.board_id == board_id)
    if namespace is not None:
        stmt = stmt.where(WorkItemRow.namespace == namespace)
    if kind is not None:
        stmt = stmt.where(WorkItemRow.kind == kind.value)
    if state is not None:
        stmt = stmt.where(WorkItemRow.state == state.value)
    if exclude_terminal:
        terminal_values = [item.value for item in TERMINAL_WORK_ITEM_STATES]
        stmt = stmt.where(WorkItemRow.state.notin_(terminal_values))
    if work_queue_id is not None:
        stmt = stmt.where(
            _assignment_text("assignee_kind") == AssigneeKind.QUEUE.value,
            _assignment_text("work_queue_id") == work_queue_id,
        )
    if assignee_flow_id is not None:
        stmt = stmt.where(
            _assignment_text("assignee_kind") == AssigneeKind.AGENT.value,
            _assignment_text("flow_id") == assignee_flow_id,
        )
    if assignee_user_id is not None:
        stmt = stmt.where(
            _assignment_text("assignee_kind") == AssigneeKind.USERS.value,
            WorkItemRow.assignment["user_ids"].contains([assignee_user_id]),
        )
    if queue_unclaimed_only:
        stmt = stmt.where(
            _assignment_text("assignee_kind") == AssigneeKind.QUEUE.value,
            _assignment_text("claimed_by_user_id").is_(None),
        )
    return stmt


def _apply_work_queue_ids_filter(
    stmt: Select[tuple[WorkItemRow]],
    work_queue_ids: list[str] | None,
) -> Select[tuple[WorkItemRow]]:
    if work_queue_ids is None:
        return stmt
    return stmt.where(
        _assignment_text("assignee_kind") == AssigneeKind.QUEUE.value,
        _assignment_text("work_queue_id").in_(work_queue_ids),
        _assignment_text("claimed_by_user_id").is_(None),
    )


def _variables_to_json(variables: VariableMap) -> JsonObject:
    return {
        key: require_json_object(entry.model_dump(mode="json"), f"variables.{key}")
        for key, entry in variables.items()
    }


def _variables_from_json(raw: JsonObject) -> VariableMap:
    return normalize_variables_map(raw)


def _attachments_to_json(attachments: list[FileRef]) -> JsonArray:
    return [
        require_json_object(file_ref.model_dump(mode="json"), "FileRef")
        for file_ref in attachments
    ]


def _resolution_from_json(raw: JsonObject) -> WorkItemResolution:
    payload = dict(raw)
    if "file_ids" in payload and "files" not in payload:
        file_ids_raw = payload.pop("file_ids")
        if isinstance(file_ids_raw, list):
            minimal_refs = minimal_file_refs_from_file_ids([str(item) for item in file_ids_raw])
            payload["files"] = [
                require_json_object(file_ref.model_dump(mode="json"), "FileRef")
                for file_ref in minimal_refs
            ]
    return WorkItemResolution.model_validate(payload)


def _work_item_to_row(item: WorkItem) -> WorkItemRow:
    assignment_json = require_json_object(
        item.assignment.model_dump(mode="json"), "WorkItemAssignment"
    )
    hooks_json: JsonArray = [
        require_json_object(hook.model_dump(mode="json"), "WorkItemHook") for hook in item.hooks
    ]
    resolution_json: JsonObject | None = (
        require_json_object(item.resolution.model_dump(mode="json"), "WorkItemResolution")
        if item.resolution is not None
        else None
    )
    links_json: JsonArray = [
        require_json_object(link.model_dump(mode="json"), "WorkItemLink") for link in item.links
    ]
    variables_json = _variables_to_json(item.variables)
    attachments_json = _attachments_to_json(item.attachments)
    return WorkItemRow(
        work_item_id=item.work_item_id,
        company_id=item.company_id,
        namespace=item.namespace,
        title=item.title,
        description=item.description,
        kind=item.kind.value,
        state=item.state.value,
        board_id=item.board_id,
        board_column_id=item.board_column_id,
        priority=item.priority.value,
        due_date=item.due_date,
        labels=list(item.labels),
        created_by=_actor_to_json(item.created_by),
        assignment=assignment_json,
        blocking=item.blocking,
        hooks=hooks_json,
        resolution=resolution_json,
        links=links_json,
        variables=variables_json,
        attachments=attachments_json,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _row_to_work_item(row: WorkItemRow) -> WorkItem:
    links = _LINKS_ADAPTER.validate_python(row.links)
    hooks = _HOOKS_ADAPTER.validate_python(row.hooks)
    resolution = (
        _resolution_from_json(require_json_object(row.resolution, "resolution"))
        if row.resolution is not None
        else None
    )
    labels = [str(label) for label in row.labels]
    variables = _variables_from_json(require_json_object(row.variables, "variables"))
    attachments = parse_file_refs(row.attachments)
    return WorkItem(
        work_item_id=row.work_item_id,
        company_id=row.company_id,
        namespace=row.namespace,
        title=row.title,
        description=row.description,
        kind=WorkItemKind(row.kind),
        state=WorkItemState(row.state),
        board_id=row.board_id,
        board_column_id=row.board_column_id,
        priority=WorkItemPriority(row.priority),
        due_date=row.due_date,
        labels=labels,
        created_by=_actor_from_json(require_json_object(row.created_by, "created_by")),
        assignment=_ASSIGNMENT_ADAPTER.validate_python(row.assignment),
        blocking=row.blocking,
        hooks=hooks,
        resolution=resolution,
        links=links,
        variables=variables,
        attachments=attachments,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _row_to_queue(row: WorkQueueRow) -> WorkQueue:
    return WorkQueue(
        work_queue_id=row.work_queue_id,
        company_id=row.company_id,
        name=row.name,
        work_queue_slug=row.slug,
        description=row.description,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _row_to_board(row: BoardRow) -> Board:
    columns = [BoardColumn.model_validate(col) for col in row.columns]
    return Board(
        board_id=row.board_id,
        company_id=row.company_id,
        namespace=row.namespace,
        board_key=row.board_key,
        name=row.name,
        columns=columns,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _row_to_comment(row: WorkItemCommentRow) -> WorkItemComment:
    return WorkItemComment(
        comment_id=row.comment_id,
        work_item_id=row.work_item_id,
        company_id=row.company_id,
        author=_actor_from_json(require_json_object(row.author, "author")),
        role=WorkItemCommentRole(row.role),
        text=row.text,
        files=parse_file_refs(row.files),
        created_at=row.created_at,
    )


class WorktrackerRepository:
    """Хранилище WorkItem, очередей, досок и комментариев `platform_worktracker`."""

    def __init__(self, db: WorktrackerDatabase) -> None:
        self._db: WorktrackerDatabase = db

    # === WorkItem ===

    async def insert_work_item(self, item: WorkItem) -> WorkItem:
        async with self._db.session() as session:
            row = _work_item_to_row(item)
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _row_to_work_item(row)

    async def get_work_item(self, company_id: str, work_item_id: str) -> WorkItem | None:
        async with self._db.session() as session:
            stmt = select(WorkItemRow).where(
                WorkItemRow.company_id == company_id,
                WorkItemRow.work_item_id == work_item_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _row_to_work_item(row) if row is not None else None

    async def save_work_item(self, item: WorkItem) -> WorkItem:
        async with self._db.session() as session:
            merged = await session.merge(_work_item_to_row(item))
            await session.commit()
            await session.refresh(merged)
            return _row_to_work_item(merged)

    async def list_work_items(
        self,
        company_id: str,
        *,
        board_id: str | None = None,
        namespace: str | None = None,
        kind: WorkItemKind | None = None,
        state: WorkItemState | None = None,
        work_queue_id: str | None = None,
        assignee_user_id: str | None = None,
        assignee_flow_id: str | None = None,
        exclude_terminal: bool = False,
        queue_unclaimed_only: bool = False,
        work_queue_ids: list[str] | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[WorkItem]:
        async with self._db.session() as session:
            stmt = select(WorkItemRow).where(WorkItemRow.company_id == company_id)
            stmt = _apply_work_item_filters(
                stmt,
                board_id=board_id,
                namespace=namespace,
                kind=kind,
                state=state,
                work_queue_id=work_queue_id,
                assignee_user_id=assignee_user_id,
                assignee_flow_id=assignee_flow_id,
                exclude_terminal=exclude_terminal,
                queue_unclaimed_only=queue_unclaimed_only,
            )
            stmt = _apply_work_queue_ids_filter(stmt, work_queue_ids)
            stmt = stmt.order_by(WorkItemRow.created_at.desc()).limit(limit).offset(offset)
            rows = list((await session.execute(stmt)).scalars().all())
            return [_row_to_work_item(row) for row in rows]

    async def count_work_items(
        self,
        company_id: str,
        *,
        board_id: str | None = None,
        namespace: str | None = None,
        kind: WorkItemKind | None = None,
        state: WorkItemState | None = None,
        work_queue_id: str | None = None,
        assignee_user_id: str | None = None,
        assignee_flow_id: str | None = None,
        exclude_terminal: bool = False,
        queue_unclaimed_only: bool = False,
        work_queue_ids: list[str] | None = None,
    ) -> int:
        async with self._db.session() as session:
            filtered = select(WorkItemRow).where(WorkItemRow.company_id == company_id)
            filtered = _apply_work_item_filters(
                filtered,
                board_id=board_id,
                namespace=namespace,
                kind=kind,
                state=state,
                work_queue_id=work_queue_id,
                assignee_user_id=assignee_user_id,
                assignee_flow_id=assignee_flow_id,
                exclude_terminal=exclude_terminal,
                queue_unclaimed_only=queue_unclaimed_only,
            )
            filtered = _apply_work_queue_ids_filter(filtered, work_queue_ids)
            count_stmt = select(func.count()).select_from(filtered.subquery())
            return (await session.execute(count_stmt)).scalar_one()

    async def find_work_item_by_correlation(
        self, company_id: str, correlation_id: str
    ) -> WorkItem | None:
        """Поиск WorkItem по correlation_id в hooks[].binding (идемпотентность HITL)."""
        async with self._db.session() as session:
            stmt = select(WorkItemRow).where(WorkItemRow.company_id == company_id)
            rows = list((await session.execute(stmt)).scalars().all())
        for row in rows:
            for hook in row.hooks:
                if not isinstance(hook, dict):
                    continue
                binding = hook.get("binding")
                if isinstance(binding, dict) and binding.get("correlation_id") == correlation_id:
                    return _row_to_work_item(row)
        return None

    async def find_work_item_by_crm_entity(
        self, company_id: str, entity_id: str
    ) -> WorkItem | None:
        """Поиск парного WorkItem по `CrmEntityLink.entity_id` (связь 1:1 с CRM-узлом)."""
        async with self._db.session() as session:
            stmt = select(WorkItemRow).where(
                WorkItemRow.company_id == company_id,
                WorkItemRow.kind == WorkItemKind.CRM_ACTIVITY.value,
            )
            rows = list((await session.execute(stmt)).scalars().all())
        for row in rows:
            for link in row.links:
                if not isinstance(link, dict):
                    continue
                if link.get("link_kind") == "crm_entity" and link.get("entity_id") == entity_id:
                    return _row_to_work_item(row)
        return None

    async def map_work_item_ids_by_crm_entities(
        self, company_id: str, entity_ids: list[str]
    ) -> dict[str, str]:
        if not entity_ids:
            return {}
        wanted = set(entity_ids)
        mapped: dict[str, str] = {}
        async with self._db.session() as session:
            stmt = select(WorkItemRow).where(
                WorkItemRow.company_id == company_id,
                WorkItemRow.kind == WorkItemKind.CRM_ACTIVITY.value,
            )
            rows = list((await session.execute(stmt)).scalars().all())
        for row in rows:
            for link in row.links:
                if not isinstance(link, dict):
                    continue
                entity_id = link.get("entity_id")
                if (
                    link.get("link_kind") == "crm_entity"
                    and isinstance(entity_id, str)
                    and entity_id in wanted
                ):
                    mapped[entity_id] = row.work_item_id
        return mapped

    async def delete_work_item(self, company_id: str, work_item_id: str) -> bool:
        async with self._db.session() as session:
            stmt = delete(WorkItemRow).where(
                WorkItemRow.company_id == company_id,
                WorkItemRow.work_item_id == work_item_id,
            )
            result = await session.execute(stmt)
            await session.commit()
            return get_rowcount(result) > 0

    # === Комментарии ===

    async def append_comment(self, comment: WorkItemComment) -> WorkItemComment:
        async with self._db.session() as session:
            row = WorkItemCommentRow(
                comment_id=comment.comment_id,
                work_item_id=comment.work_item_id,
                company_id=comment.company_id,
                author=_actor_to_json(comment.author),
                role=comment.role.value,
                text=comment.text,
                files=_attachments_to_json(comment.files),
                created_at=comment.created_at,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _row_to_comment(row)

    async def list_comments(self, company_id: str, work_item_id: str) -> list[WorkItemComment]:
        async with self._db.session() as session:
            stmt = (
                select(WorkItemCommentRow)
                .where(
                    WorkItemCommentRow.company_id == company_id,
                    WorkItemCommentRow.work_item_id == work_item_id,
                )
                .order_by(WorkItemCommentRow.created_at.asc())
            )
            rows = list((await session.execute(stmt)).scalars().all())
            return [_row_to_comment(row) for row in rows]

    # === Очереди ===

    async def insert_queue(self, queue: WorkQueue) -> WorkQueue:
        async with self._db.session() as session:
            row = WorkQueueRow(
                work_queue_id=queue.work_queue_id,
                company_id=queue.company_id,
                name=queue.name,
                slug=queue.work_queue_slug,
                description=queue.description,
                created_at=queue.created_at,
                updated_at=queue.updated_at,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _row_to_queue(row)

    async def save_queue(self, queue: WorkQueue) -> WorkQueue:
        async with self._db.session() as session:
            row = WorkQueueRow(
                work_queue_id=queue.work_queue_id,
                company_id=queue.company_id,
                name=queue.name,
                slug=queue.work_queue_slug,
                description=queue.description,
                created_at=queue.created_at,
                updated_at=queue.updated_at,
            )
            merged = await session.merge(row)
            await session.commit()
            await session.refresh(merged)
            return _row_to_queue(merged)

    async def get_queue(self, company_id: str, work_queue_id: str) -> WorkQueue | None:
        async with self._db.session() as session:
            stmt = select(WorkQueueRow).where(
                WorkQueueRow.company_id == company_id,
                WorkQueueRow.work_queue_id == work_queue_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _row_to_queue(row) if row is not None else None

    async def get_queue_by_slug(self, company_id: str, slug: str) -> WorkQueue | None:
        async with self._db.session() as session:
            stmt = select(WorkQueueRow).where(
                WorkQueueRow.company_id == company_id,
                WorkQueueRow.slug == slug,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _row_to_queue(row) if row is not None else None

    async def list_queues(self, company_id: str) -> list[WorkQueue]:
        async with self._db.session() as session:
            stmt = (
                select(WorkQueueRow)
                .where(WorkQueueRow.company_id == company_id)
                .order_by(WorkQueueRow.created_at.asc())
            )
            rows = list((await session.execute(stmt)).scalars().all())
            return [_row_to_queue(row) for row in rows]

    async def add_queue_member(self, member: WorkQueueMember, company_id: str) -> None:
        member_kind, member_ref = _member_kind_ref(member.member)
        async with self._db.session() as session:
            row = WorkQueueMemberRow(
                work_queue_id=member.work_queue_id,
                member_kind=member_kind,
                member_ref=member_ref,
                company_id=company_id,
                role=member.role,
            )
            merged = await session.merge(row)
            session.add(merged)
            await session.commit()

    async def remove_queue_member(self, work_queue_id: str, member: WorkActor) -> bool:
        member_kind, member_ref = _member_kind_ref(member)
        async with self._db.session() as session:
            stmt = delete(WorkQueueMemberRow).where(
                WorkQueueMemberRow.work_queue_id == work_queue_id,
                WorkQueueMemberRow.member_kind == member_kind,
                WorkQueueMemberRow.member_ref == member_ref,
            )
            result = await session.execute(stmt)
            await session.commit()
            return get_rowcount(result) > 0

    async def list_queue_ids_for_member(self, company_id: str, user_id: str) -> list[str]:
        async with self._db.session() as session:
            stmt = select(WorkQueueMemberRow.work_queue_id).where(
                WorkQueueMemberRow.company_id == company_id,
                WorkQueueMemberRow.member_kind == ActorKind.USER.value,
                WorkQueueMemberRow.member_ref == user_id,
            )
            rows = list((await session.execute(stmt)).scalars().all())
            return rows

    async def list_queue_members(self, work_queue_id: str) -> list[WorkQueueMember]:
        async with self._db.session() as session:
            stmt = select(WorkQueueMemberRow).where(
                WorkQueueMemberRow.work_queue_id == work_queue_id
            )
            rows = list((await session.execute(stmt)).scalars().all())
            return [
                WorkQueueMember(
                    work_queue_id=row.work_queue_id,
                    member=_member_actor(row.member_kind, row.member_ref),
                    role=row.role,
                )
                for row in rows
            ]

    async def is_member(self, work_queue_id: str, member: WorkActor) -> bool:
        member_kind, member_ref = _member_kind_ref(member)
        async with self._db.session() as session:
            stmt = select(WorkQueueMemberRow.member_ref).where(
                WorkQueueMemberRow.work_queue_id == work_queue_id,
                WorkQueueMemberRow.member_kind == member_kind,
                WorkQueueMemberRow.member_ref == member_ref,
            )
            return (await session.execute(stmt)).scalar_one_or_none() is not None

    # === Доски ===

    async def insert_board(self, board: Board) -> Board:
        async with self._db.session() as session:
            row = BoardRow(
                board_id=board.board_id,
                company_id=board.company_id,
                namespace=board.namespace,
                board_key=board.board_key,
                name=board.name,
                columns=[col.model_dump(mode="json") for col in board.columns],
                created_at=board.created_at,
                updated_at=board.updated_at,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _row_to_board(row)

    async def get_board(self, company_id: str, board_id: str) -> Board | None:
        async with self._db.session() as session:
            stmt = select(BoardRow).where(
                BoardRow.company_id == company_id,
                BoardRow.board_id == board_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _row_to_board(row) if row is not None else None

    async def list_boards(
        self, company_id: str, *, namespace: str | None = None
    ) -> list[Board]:
        async with self._db.session() as session:
            stmt = select(BoardRow).where(BoardRow.company_id == company_id)
            if namespace is not None:
                stmt = stmt.where(BoardRow.namespace == namespace)
            stmt = stmt.order_by(BoardRow.created_at.asc())
            rows = list((await session.execute(stmt)).scalars().all())
            return [_row_to_board(row) for row in rows]

    async def save_board(self, board: Board) -> Board:
        async with self._db.session() as session:
            row = BoardRow(
                board_id=board.board_id,
                company_id=board.company_id,
                namespace=board.namespace,
                board_key=board.board_key,
                name=board.name,
                columns=[col.model_dump(mode="json") for col in board.columns],
                created_at=board.created_at,
                updated_at=board.updated_at,
            )
            merged = await session.merge(row)
            await session.commit()
            await session.refresh(merged)
            return _row_to_board(merged)


__all__ = ["WorktrackerRepository"]
