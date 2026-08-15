"""
WorkItemService — чистая стейт-машина и валидация гибкого ядра задач.

Сервис нейтрален: репозиторий + правила переходов + публикация событий на
шину `platform:events`. Назначение задачи — first-class и сменяемое
(`reassign`) для любого `kind`; HITL отличается `blocking=True` и binding
в `hooks` (resume читает consumer group `flows` по `worktracker/work_item/completed`).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import Field

from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.files.file_ref import FileRef
from core.identity.flow_employee import is_flow_employee_user_id
from core.logging import get_logger
from core.variables.models import VariableMap, normalize_variables_map
from core.websocket.publisher import Notification, NotificationType, notify_user
from core.worktracker.events import (
    WORK_ITEM_COMMENT_CREATED,
    WORK_ITEM_COMPLETED,
    WORK_ITEM_CREATED,
    WORK_ITEM_MOVED,
    WORK_ITEM_UPDATED,
    WorkItemEventType,
    WorkItemRealtimeEvent,
    publish_work_item_assigned,
    publish_work_item_events,
)
from core.worktracker.hook_dispatcher import hook_dispatch_internal_user_id
from core.worktracker.models import (
    TERMINAL_WORK_ITEM_STATES,
    Board,
    BoardColumn,
    QueueAssignment,
    UnassignedAssignment,
    UserActor,
    UsersAssignment,
    WorkActor,
    WorkItem,
    WorkItemAssignment,
    WorkItemComment,
    WorkItemCommentRole,
    WorkItemHook,
    WorkItemInteractionSpec,
    WorkItemKind,
    WorkItemLink,
    WorkItemPriority,
    WorkItemResolution,
    WorkItemState,
    WorkQueue,
    WorkQueueMember,
    WorktrackerModel,
    build_generic_board_columns,
)
from core.worktracker.queue_access import WorkQueueAccessPort, WorkQueueMemberRelation
from core.worktracker.repository import WorktrackerRepository

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkItemCompletion:
    """Результат завершения: задача + признак первого терминала."""

    def __init__(self, work_item: WorkItem, newly_terminal: bool) -> None:
        self.work_item: WorkItem = work_item
        self.newly_terminal: bool = newly_terminal


class WorkItemMineSummary(WorktrackerModel):
    assigned_open_count: int = Field(..., ge=0)
    queue_inbox_count: int = Field(..., ge=0)
    work_queue_ids: list[str] = Field(default_factory=list)


class WorkItemService:
    """Бизнес-логика гибкого ядра задач."""

    def __init__(
        self,
        repository: WorktrackerRepository,
        queue_access: WorkQueueAccessPort,
        authz: AuthzService,
    ) -> None:
        self._repo: WorktrackerRepository = repository
        self._queue_access: WorkQueueAccessPort = queue_access
        self._authz: AuthzService = authz

    # === Чтение ===

    async def get(self, company_id: str, work_item_id: str) -> WorkItem:
        item = await self._repo.get_work_item(company_id, work_item_id)
        if item is None:
            raise ValueError(f"WorkItem {work_item_id!r} не найден")
        return item

    async def list(
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
        return await self._repo.list_work_items(
            company_id,
            board_id=board_id,
            namespace=namespace,
            kind=kind,
            state=state,
            work_queue_id=work_queue_id,
            assignee_user_id=assignee_user_id,
            assignee_flow_id=assignee_flow_id,
            exclude_terminal=exclude_terminal,
            queue_unclaimed_only=queue_unclaimed_only,
            work_queue_ids=work_queue_ids,
            limit=limit,
            offset=offset,
        )

    async def count(
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
        return await self._repo.count_work_items(
            company_id,
            board_id=board_id,
            namespace=namespace,
            kind=kind,
            state=state,
            work_queue_id=work_queue_id,
            assignee_user_id=assignee_user_id,
            assignee_flow_id=assignee_flow_id,
            exclude_terminal=exclude_terminal,
            queue_unclaimed_only=queue_unclaimed_only,
            work_queue_ids=work_queue_ids,
        )

    async def mine_summary(self, company_id: str, user_id: str) -> WorkItemMineSummary:
        assigned_open_count = await self.count(
            company_id,
            assignee_user_id=user_id,
            exclude_terminal=True,
        )
        queue_ids = await self._queue_access.list_viewable_queue_ids(user_id=user_id)
        company_queue_ids = {
            queue.work_queue_id for queue in await self._repo.list_queues(company_id)
        }
        queue_ids = [qid for qid in queue_ids if qid in company_queue_ids]
        queue_inbox_count = 0
        if queue_ids:
            queue_inbox_count = await self.count(
                company_id,
                exclude_terminal=True,
                queue_unclaimed_only=True,
                work_queue_ids=queue_ids,
            )
        return WorkItemMineSummary(
            assigned_open_count=assigned_open_count,
            queue_inbox_count=queue_inbox_count,
            work_queue_ids=queue_ids,
        )

    async def map_work_item_ids_by_crm_entities(
        self, company_id: str, entity_ids: list[str]
    ) -> dict[str, str]:
        return await self._repo.map_work_item_ids_by_crm_entities(company_id, entity_ids)

    async def find_by_completion_correlation(
        self, company_id: str, correlation_id: str
    ) -> WorkItem | None:
        """Поиск задачи по correlation_id в hook.binding (идемпотентность HITL)."""
        return await self._repo.find_work_item_by_correlation(company_id, correlation_id)

    async def find_by_crm_entity(self, company_id: str, entity_id: str) -> WorkItem | None:
        """Парный WorkItem CRM-узла задачи (связь 1:1 через CrmEntityLink)."""
        return await self._repo.find_work_item_by_crm_entity(company_id, entity_id)

    async def delete(self, *, company_id: str, work_item_id: str) -> bool:
        return await self._repo.delete_work_item(company_id, work_item_id)

    # === Создание ===

    async def create(
        self,
        *,
        company_id: str,
        title: str,
        created_by: WorkActor,
        description: str = "",
        kind: WorkItemKind = WorkItemKind.GENERIC,
        namespace: str | None = None,
        board_id: str | None = None,
        board_column_id: str | None = None,
        priority: WorkItemPriority = WorkItemPriority.NORMAL,
        due_date: datetime | None = None,
        labels: list[str] | None = None,
        assignment: WorkItemAssignment | None = None,
        blocking: bool = False,
        interaction: WorkItemInteractionSpec | None = None,
        hooks: list[WorkItemHook] | None = None,
        links: list[WorkItemLink] | None = None,
        variables: VariableMap | None = None,
        attachments: list[FileRef] | None = None,
    ) -> WorkItem:
        state, resolved_column_id = await self._resolve_board_placement(
            company_id, board_id, board_column_id
        )
        now = _utcnow()
        item = WorkItem(
            work_item_id=f"wi_{uuid.uuid4().hex}",
            company_id=company_id,
            namespace=namespace,
            title=title,
            description=description,
            kind=kind,
            state=state,
            board_id=board_id,
            board_column_id=resolved_column_id,
            priority=priority,
            due_date=due_date,
            labels=labels or [],
            created_by=created_by,
            assignment=assignment if assignment is not None else UnassignedAssignment(),
            blocking=blocking,
            interaction=interaction,
            hooks=hooks or [],
            resolution=None,
            links=links or [],
            variables=variables or {},
            attachments=attachments or [],
            created_at=now,
            updated_at=now,
        )
        saved = await self._repo.insert_work_item(item)
        await self._publish(saved, WORK_ITEM_CREATED)
        await self._after_assignment_change(saved)
        logger.info(
            "worktracker.work_item.created",
            work_item_id=saved.work_item_id,
            kind=saved.kind.value,
            blocking=saved.blocking,
        )
        return saved

    async def create_manual_task(
        self,
        *,
        company_id: str,
        title: str,
        created_by: WorkActor,
        description: str = "",
        kind: WorkItemKind = WorkItemKind.GENERIC,
        namespace: str | None = None,
        board_id: str | None = None,
        board_column_id: str | None = None,
        priority: WorkItemPriority = WorkItemPriority.NORMAL,
        due_date: datetime | None = None,
        labels: list[str] | None = None,
        assignment: WorkItemAssignment | None = None,
        blocking: bool = False,
        links: list[WorkItemLink] | None = None,
        variables: VariableMap | None = None,
        attachments: list[FileRef] | None = None,
    ) -> WorkItem:
        """Создание задачи с доской generic: UI (UserActor → self-assign) или system."""
        resolved_assignment = assignment
        if resolved_assignment is None:
            if isinstance(created_by, UserActor):
                resolved_assignment = UsersAssignment(user_ids=[created_by.user_id])
            else:
                resolved_assignment = UnassignedAssignment()
        resolved_board_id = board_id
        if resolved_board_id is None:
            board = await self.ensure_generic_board(company_id=company_id, namespace=namespace)
            resolved_board_id = board.board_id
        return await self.create(
            company_id=company_id,
            title=title,
            created_by=created_by,
            description=description,
            kind=kind,
            namespace=namespace,
            board_id=resolved_board_id,
            board_column_id=board_column_id,
            priority=priority,
            due_date=due_date,
            labels=labels,
            assignment=resolved_assignment,
            blocking=blocking,
            links=links,
            variables=variables,
            attachments=attachments,
        )

    # === Изменение ===

    async def update(
        self,
        *,
        company_id: str,
        work_item_id: str,
        title: str | None = None,
        description: str | None = None,
        priority: WorkItemPriority | None = None,
        due_date: datetime | None = None,
        labels: list[str] | None = None,
        links: list[WorkItemLink] | None = None,
        variables: VariableMap | None = None,
        attachments: list[FileRef] | None = None,
    ) -> WorkItem:
        item = await self.get(company_id, work_item_id)
        if title is not None:
            item.title = title
        if description is not None:
            item.description = description
        if priority is not None:
            item.priority = priority
        if due_date is not None:
            item.due_date = due_date
        if labels is not None:
            item.labels = labels
        if links is not None:
            item.links = links
        if variables is not None:
            item.variables = normalize_variables_map(variables)
        if attachments is not None:
            item.attachments = list(attachments)
        item.updated_at = _utcnow()
        saved = await self._repo.save_work_item(item)
        await self._publish(saved, WORK_ITEM_UPDATED)
        if title is not None or description is not None:
            await self._notify_assignees(saved, NotificationType.WORK_ITEM_UPDATED)
        return saved

    async def reassign(
        self,
        *,
        company_id: str,
        work_item_id: str,
        assignment: WorkItemAssignment,
    ) -> WorkItem:
        """Сменить исполнителя любой non-terminal задачи (человек/очередь/агент).

        Работает для всех kind, включая operator_handoff (оператор -> flow и обратно).
        """
        item = await self.get(company_id, work_item_id)
        if item.state in TERMINAL_WORK_ITEM_STATES:
            raise ValueError(
                f"WorkItem {work_item_id!r} в терминальном состоянии {item.state.value!r}"
            )
        item.assignment = assignment
        item.updated_at = _utcnow()
        saved = await self._repo.save_work_item(item)
        await self._publish(saved, WORK_ITEM_UPDATED)
        await self._after_assignment_change(saved)
        return saved

    async def move(
        self,
        *,
        company_id: str,
        work_item_id: str,
        board_column_id: str | None = None,
        state: WorkItemState | None = None,
    ) -> WorkItem:
        item = await self.get(company_id, work_item_id)
        if item.state in TERMINAL_WORK_ITEM_STATES:
            raise ValueError(
                f"WorkItem {work_item_id!r} в терминальном состоянии {item.state.value!r}"
            )
        target_state = state
        if board_column_id is not None:
            column = await self._require_column(company_id, item.board_id, board_column_id)
            item.board_column_id = board_column_id
            target_state = column.state
        if target_state is not None:
            self._assert_transition(item.state)
            item.state = target_state
        item.updated_at = _utcnow()
        saved = await self._repo.save_work_item(item)
        await self._publish(saved, WORK_ITEM_MOVED)
        return saved

    async def claim(
        self,
        *,
        company_id: str,
        work_item_id: str,
        user_id: str,
    ) -> WorkItem:
        item = await self.get(company_id, work_item_id)
        if not isinstance(item.assignment, QueueAssignment):
            raise ValueError("claim доступен только для задач с очередью")
        if (
            item.assignment.claimed_by_user_id is not None
            and item.assignment.claimed_by_user_id != user_id
        ):
            raise ValueError("Задача уже взята другим участником очереди")
        if not await self._authz.can_view(
            AuthzObject.work_queue(item.assignment.work_queue_id), user_id=user_id
        ):
            raise PermissionError("Нет доступа к очереди этой задачи")
        item.assignment = QueueAssignment(
            work_queue_id=item.assignment.work_queue_id,
            claimed_by_user_id=user_id,
        )
        if item.state == WorkItemState.OPEN:
            item.state = WorkItemState.IN_PROGRESS
        item.updated_at = _utcnow()
        saved = await self._repo.save_work_item(item)
        await self._publish(saved, WORK_ITEM_UPDATED)
        return saved

    async def complete(
        self,
        *,
        company_id: str,
        work_item_id: str,
        resolution: WorkItemResolution | None = None,
        terminal_state: WorkItemState = WorkItemState.DONE,
    ) -> WorkItemCompletion:
        if terminal_state not in TERMINAL_WORK_ITEM_STATES:
            raise ValueError(f"{terminal_state.value!r} не терминальное состояние")
        item = await self.get(company_id, work_item_id)
        if item.state in TERMINAL_WORK_ITEM_STATES:
            return WorkItemCompletion(item, newly_terminal=False)
        item.state = terminal_state
        if resolution is not None:
            item.resolution = resolution
        item.updated_at = _utcnow()
        saved = await self._repo.save_work_item(item)
        await self._publish(saved, WORK_ITEM_COMPLETED)
        logger.info(
            "worktracker.work_item.completed",
            work_item_id=saved.work_item_id,
            state=saved.state.value,
        )
        return WorkItemCompletion(saved, newly_terminal=True)

    async def cancel(self, *, company_id: str, work_item_id: str) -> WorkItemCompletion:
        return await self.complete(
            company_id=company_id,
            work_item_id=work_item_id,
            terminal_state=WorkItemState.CANCELLED,
        )

    async def reject(
        self, *, company_id: str, work_item_id: str, reason: str = ""
    ) -> WorkItemCompletion:
        return await self.complete(
            company_id=company_id,
            work_item_id=work_item_id,
            resolution=WorkItemResolution(text=reason),
            terminal_state=WorkItemState.FAILED,
        )

    # === Комментарии ===

    async def add_comment(
        self,
        *,
        company_id: str,
        work_item_id: str,
        author: WorkActor,
        role: WorkItemCommentRole = WorkItemCommentRole.SYSTEM,
        text: str = "",
        files: list[FileRef] | None = None,
    ) -> WorkItemComment:
        item = await self.get(company_id, work_item_id)
        comment = WorkItemComment(
            comment_id=f"wic_{uuid.uuid4().hex}",
            work_item_id=work_item_id,
            company_id=company_id,
            author=author,
            role=role,
            text=text,
            files=files or [],
            created_at=_utcnow(),
        )
        saved = await self._repo.append_comment(comment)
        await publish_work_item_events(
            [
                WorkItemRealtimeEvent(
                    type=WORK_ITEM_COMMENT_CREATED,
                    payload={
                        "work_item_id": work_item_id,
                        "comment": saved.model_dump(mode="json"),
                    },
                    company_id=company_id,
                    recipient_user_ids=self._recipient_user_ids(item),
                )
            ]
        )
        author_user_id = author.user_id if isinstance(author, UserActor) else None
        await self._notify_assignees(
            item,
            NotificationType.WORK_ITEM_COMMENT,
            message=text,
            skip_user_ids={author_user_id} if author_user_id is not None else None,
        )
        return saved

    async def list_comments(self, company_id: str, work_item_id: str) -> list[WorkItemComment]:
        return await self._repo.list_comments(company_id, work_item_id)

    # === Очереди ===

    async def create_queue(
        self,
        *,
        company_id: str,
        name: str,
        slug: str,
        description: str | None = None,
        creator: WorkActor | None = None,
    ) -> WorkQueue:
        existing = await self._repo.get_queue_by_slug(company_id, slug)
        if existing is not None:
            raise ValueError(f"Очередь со slug {slug!r} уже существует")
        if creator is not None and not isinstance(creator, UserActor):
            raise ValueError("owner очереди должен быть UserActor")
        if isinstance(creator, UserActor):
            owner_user_id = creator.user_id
        else:
            owner_user_id = await self._queue_access.resolve_company_admin_owner(company_id)
        now = _utcnow()
        queue = WorkQueue(
            work_queue_id=f"wq_{uuid.uuid4().hex}",
            company_id=company_id,
            name=name,
            work_queue_slug=slug,
            description=description,
            owner_user_id=owner_user_id,
            created_at=now,
            updated_at=now,
        )
        saved = await self._repo.insert_queue(queue)
        try:
            await self._queue_access.sync_queue_created(
                saved.work_queue_id,
                company_id=company_id,
                owner_user_id=owner_user_id,
            )
        except Exception:
            await self._queue_access.sync_queue_deleted(saved.work_queue_id)
            await self._repo.delete_queue(company_id, saved.work_queue_id)
            raise
        return saved

    async def delete_queue(
        self,
        *,
        company_id: str,
        work_queue_id: str,
        actor_user_id: str,
    ) -> None:
        await self._authz.require_can_admin(
            AuthzObject.work_queue(work_queue_id), user_id=actor_user_id
        )
        queue = await self._repo.get_queue(company_id, work_queue_id)
        if queue is None:
            raise ValueError(f"Очередь {work_queue_id!r} не найдена")
        await self._queue_access.sync_queue_deleted(work_queue_id)
        await self._repo.delete_queue(company_id, work_queue_id)

    async def update_queue(
        self,
        *,
        company_id: str,
        work_queue_id: str,
        name: str | None = None,
        description: str | None = None,
        actor_user_id: str,
    ) -> WorkQueue:
        await self._authz.require_can_admin(
            AuthzObject.work_queue(work_queue_id), user_id=actor_user_id
        )
        queue = await self._repo.get_queue(company_id, work_queue_id)
        if queue is None:
            raise ValueError(f"Очередь {work_queue_id!r} не найдена")
        if name is not None:
            queue.name = name
        if description is not None:
            queue.description = description
        queue.updated_at = _utcnow()
        return await self._repo.save_queue(queue)

    async def get_queue_by_slug(self, company_id: str, slug: str) -> WorkQueue:
        queue = await self._repo.get_queue_by_slug(company_id, slug)
        if queue is None:
            raise ValueError(f"Очередь со slug {slug!r} не найдена")
        return queue

    async def list_queues(self, company_id: str, *, user_id: str) -> list[WorkQueue]:
        viewable = set(await self._queue_access.list_viewable_queue_ids(user_id=user_id))
        return [
            queue
            for queue in await self._repo.list_queues(company_id)
            if queue.work_queue_id in viewable
        ]

    async def add_queue_member(
        self,
        *,
        company_id: str,
        work_queue_id: str,
        member: WorkActor,
        role: WorkQueueMemberRelation = "member",
        actor_user_id: str | None = None,
    ) -> WorkQueueMember:
        _ = company_id
        if not isinstance(member, UserActor):
            raise ValueError("участник очереди должен быть UserActor")
        if actor_user_id is not None:
            await self._authz.require_can_admin(
                AuthzObject.work_queue(work_queue_id), user_id=actor_user_id
            )
        await self._queue_access.set_member(
            work_queue_id, user_id=member.user_id, relation=role
        )
        return WorkQueueMember(work_queue_id=work_queue_id, member=member, role=role)

    async def remove_queue_member(
        self,
        *,
        work_queue_id: str,
        member: WorkActor,
        actor_user_id: str,
    ) -> bool:
        if not isinstance(member, UserActor):
            raise ValueError("участник очереди должен быть UserActor")
        await self._authz.require_can_admin(
            AuthzObject.work_queue(work_queue_id), user_id=actor_user_id
        )
        if not await self._authz.can_view(
            AuthzObject.work_queue(work_queue_id), user_id=member.user_id
        ):
            return False
        await self._queue_access.remove_member(work_queue_id, user_id=member.user_id)
        return True

    async def list_queue_members(self, work_queue_id: str) -> list[WorkQueueMember]:
        rows = await self._queue_access.list_member_rows(work_queue_id)
        return [
            WorkQueueMember(
                work_queue_id=work_queue_id,
                member=UserActor(user_id=user_id),
                role=role,
            )
            for user_id, role in rows
        ]

    async def is_member(self, work_queue_id: str, member: WorkActor) -> bool:
        if not isinstance(member, UserActor):
            return False
        return await self._authz.can_view(
            AuthzObject.work_queue(work_queue_id), user_id=member.user_id
        )

    async def operator_authorized(self, item: WorkItem, user_id: str) -> bool:
        """Оператор допущен к задаче: участник очереди и (если claim) он же claimed."""
        assignment = item.assignment
        if not isinstance(assignment, QueueAssignment):
            return False
        if (
            assignment.claimed_by_user_id is not None
            and assignment.claimed_by_user_id != user_id
        ):
            return False
        return await self._authz.can_view(
            AuthzObject.work_queue(assignment.work_queue_id), user_id=user_id
        )

    # === Доски ===

    async def create_board(
        self,
        *,
        company_id: str,
        name: str,
        columns: list[BoardColumn],
        namespace: str | None = None,
        board_key: str = "generic",
    ) -> Board:
        resolved_columns = columns if columns else build_generic_board_columns()
        now = _utcnow()
        board = Board(
            board_id=f"wb_{uuid.uuid4().hex}",
            company_id=company_id,
            namespace=namespace,
            board_key=board_key,
            name=name,
            columns=resolved_columns,
            created_at=now,
            updated_at=now,
        )
        return await self._repo.insert_board(board)

    async def update_board(
        self,
        *,
        company_id: str,
        board_id: str,
        name: str | None = None,
        columns: list[BoardColumn] | None = None,
    ) -> Board:
        board = await self.get_board(company_id, board_id)
        if name is not None:
            board.name = name
        if columns is not None:
            board.columns = columns
        board.updated_at = _utcnow()
        return await self._repo.save_board(board)

    async def get_board(self, company_id: str, board_id: str) -> Board:
        board = await self._repo.get_board(company_id, board_id)
        if board is None:
            raise ValueError(f"Доска {board_id!r} не найдена")
        return board

    async def list_boards(self, company_id: str, *, namespace: str | None = None) -> list[Board]:
        boards = await self._repo.list_boards(company_id, namespace=namespace)
        if boards:
            return boards
        return [await self.ensure_generic_board(company_id=company_id, namespace=namespace)]

    async def ensure_generic_board(
        self,
        *,
        company_id: str,
        namespace: str | None = None,
    ) -> Board:
        return await self.resolve_board_for(
            company_id=company_id,
            board_key="generic",
            default_name="Tasks",
            default_columns=build_generic_board_columns(),
            namespace=namespace,
        )

    async def resolve_board_for(
        self,
        *,
        company_id: str,
        board_key: str,
        default_name: str,
        default_columns: list[BoardColumn],
        namespace: str | None = None,
    ) -> Board:
        """Найти доску по (namespace, board_key) или создать с дефолтными колонками."""
        boards = await self._repo.list_boards(company_id, namespace=namespace)
        for board in boards:
            if board.board_key == board_key:
                return board
        return await self.create_board(
            company_id=company_id,
            name=default_name,
            columns=default_columns,
            namespace=namespace,
            board_key=board_key,
        )

    # === Внутреннее ===

    async def _resolve_board_placement(
        self, company_id: str, board_id: str | None, board_column_id: str | None
    ) -> tuple[WorkItemState, str | None]:
        if board_id is None:
            return WorkItemState.OPEN, None
        board = await self.get_board(company_id, board_id)
        if not board.columns:
            return WorkItemState.OPEN, None
        if board_column_id is not None:
            column = self._find_column(board, board_column_id)
            return column.state, column.board_column_id
        first = board.columns[0]
        return first.state, first.board_column_id

    async def _require_column(
        self, company_id: str, board_id: str | None, board_column_id: str
    ) -> BoardColumn:
        if board_id is None:
            raise ValueError("Задача без доски не может иметь колонку")
        board = await self.get_board(company_id, board_id)
        return self._find_column(board, board_column_id)

    @staticmethod
    def _find_column(board: Board, board_column_id: str) -> BoardColumn:
        for column in board.columns:
            if column.board_column_id == board_column_id:
                return column
        raise ValueError(
            f"Колонка {board_column_id!r} отсутствует на доске {board.board_id!r}"
        )

    @staticmethod
    def _assert_transition(current: WorkItemState) -> None:
        if current in TERMINAL_WORK_ITEM_STATES:
            raise ValueError(
                f"Переход из терминального состояния {current.value!r} запрещён"
            )

    async def _after_assignment_change(self, item: WorkItem) -> None:
        await self._notify_assignees(item, NotificationType.WORK_ITEM_ASSIGNED)
        await publish_work_item_assigned(
            item,
            assigned_by_user_id=hook_dispatch_internal_user_id(item),
        )

    async def _publish(self, item: WorkItem, event_type: WorkItemEventType) -> None:
        company_broadcast_types: frozenset[WorkItemEventType] = frozenset(
            {
                WORK_ITEM_CREATED,
                WORK_ITEM_UPDATED,
                WORK_ITEM_MOVED,
                WORK_ITEM_COMPLETED,
            }
        )
        recipients = (
            None
            if event_type in company_broadcast_types
            else self._recipient_user_ids(item)
        )
        await publish_work_item_events(
            [
                WorkItemRealtimeEvent(
                    type=event_type,
                    payload={"work_item": item.model_dump(mode="json")},
                    company_id=item.company_id,
                    recipient_user_ids=recipients,
                )
            ]
        )

    @staticmethod
    def _recipient_user_ids(item: WorkItem) -> list[str] | None:
        if isinstance(item.assignment, UsersAssignment):
            return list(item.assignment.user_ids)
        return None

    @staticmethod
    async def _notify_assignees(
        item: WorkItem,
        notification_type: NotificationType,
        *,
        message: str | None = None,
        skip_user_ids: set[str] | None = None,
    ) -> None:
        if not isinstance(item.assignment, UsersAssignment):
            return
        for user_id in item.assignment.user_ids:
            if is_flow_employee_user_id(user_id):
                continue
            if skip_user_ids is not None and user_id in skip_user_ids:
                continue
            await notify_user(
                user_id,
                Notification(
                    type=notification_type,
                    title=item.title,
                    message=message if message is not None else item.description,
                    service="worktracker",
                    action_url=f"/worktracker/tasks/{item.work_item_id}",
                    data={"work_item_id": item.work_item_id},
                ),
            )

__all__ = ["WorkItemService", "WorkItemCompletion", "WorkItemMineSummary"]
