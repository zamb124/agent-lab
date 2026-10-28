"""WorktrackerClient — thin typed client for work_* tools over WorkItemService."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from core.files.file_ref import FileRef
from core.variables.models import VariableMap
from core.worktracker.models import (
    Board,
    BoardColumn,
    WorkActor,
    WorkItem,
    WorkItemAssignment,
    WorkItemComment,
    WorkItemCommentRole,
    WorkItemKind,
    WorkItemLink,
    WorkItemPriority,
    WorkItemResolution,
    WorkItemState,
    WorkQueue,
    WorkQueueMember,
)
from core.worktracker.service import (
    WorkItemCompletion,
    WorkItemMineSummary,
    WorkItemService,
)


class WorktrackerClient:
    """work_item / work_queue / work_board tools → WorkItemService."""

    _service: WorkItemService

    def __init__(self, service: WorkItemService) -> None:
        self._service = service

    async def get(self, company_id: str, work_item_id: str) -> WorkItem:
        return await WorkItem.require_in_company(company_id, work_item_id)

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
        return await WorkItem.list_created_desc(
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

    async def mine_summary(self, company_id: str, user_id: str) -> WorkItemMineSummary:
        return await self._service.mine_summary(company_id, user_id)

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
        return await self._service.create_manual_task(
            company_id=company_id,
            title=title,
            created_by=created_by,
            description=description,
            kind=kind,
            namespace=namespace,
            board_id=board_id,
            board_column_id=board_column_id,
            priority=priority,
            due_date=due_date,
            labels=labels,
            assignment=assignment,
            blocking=blocking,
            links=links,
            variables=variables,
            attachments=attachments,
        )

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
        return await self._service.update(
            company_id=company_id,
            work_item_id=work_item_id,
            title=title,
            description=description,
            priority=priority,
            due_date=due_date,
            labels=labels,
            links=links,
            variables=variables,
            attachments=attachments,
        )

    async def reassign(
        self,
        *,
        company_id: str,
        work_item_id: str,
        assignment: WorkItemAssignment,
    ) -> WorkItem:
        return await self._service.reassign(
            company_id=company_id,
            work_item_id=work_item_id,
            assignment=assignment,
        )

    async def move(
        self,
        *,
        company_id: str,
        work_item_id: str,
        board_column_id: str | None = None,
        state: WorkItemState | None = None,
    ) -> WorkItem:
        return await self._service.move(
            company_id=company_id,
            work_item_id=work_item_id,
            board_column_id=board_column_id,
            state=state,
        )

    async def claim(
        self,
        *,
        company_id: str,
        work_item_id: str,
        user_id: str,
    ) -> WorkItem:
        return await self._service.claim(
            company_id=company_id,
            work_item_id=work_item_id,
            user_id=user_id,
        )

    async def complete(
        self,
        *,
        company_id: str,
        work_item_id: str,
        resolution: WorkItemResolution | None = None,
        terminal_state: WorkItemState = WorkItemState.DONE,
    ) -> WorkItemCompletion:
        return await self._service.complete(
            company_id=company_id,
            work_item_id=work_item_id,
            resolution=resolution,
            terminal_state=terminal_state,
        )

    async def cancel(self, *, company_id: str, work_item_id: str) -> WorkItemCompletion:
        return await self._service.cancel(company_id=company_id, work_item_id=work_item_id)

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
        return await self._service.add_comment(
            company_id=company_id,
            work_item_id=work_item_id,
            author=author,
            role=role,
            text=text,
            files=files,
        )

    async def list_comments(
        self,
        *,
        company_id: str,
        work_item_id: str,
    ) -> list[WorkItemComment]:
        return await WorkItemComment.list_for_work_item(company_id, work_item_id)

    async def get_queue_by_slug(self, company_id: str, slug: str) -> WorkQueue:
        return await self._service.get_queue_by_slug(company_id, slug)

    async def list_queues(self, company_id: str, *, user_id: str) -> list[WorkQueue]:
        return await self._service.list_queues(company_id, user_id=user_id)

    async def create_queue(
        self,
        *,
        company_id: str,
        name: str,
        slug: str,
        description: str | None = None,
        creator: WorkActor | None = None,
    ) -> WorkQueue:
        return await self._service.create_queue(
            company_id=company_id,
            name=name,
            slug=slug,
            description=description,
            creator=creator,
        )

    async def update_queue(
        self,
        *,
        company_id: str,
        work_queue_id: str,
        name: str | None = None,
        description: str | None = None,
        actor_user_id: str,
    ) -> WorkQueue:
        return await self._service.update_queue(
            company_id=company_id,
            work_queue_id=work_queue_id,
            name=name,
            description=description,
            actor_user_id=actor_user_id,
        )

    async def list_queue_members(self, work_queue_id: str) -> list[WorkQueueMember]:
        return await self._service.list_queue_members(work_queue_id)

    async def add_queue_member(
        self,
        *,
        company_id: str,
        work_queue_id: str,
        member: WorkActor,
        role: Literal["owner", "member"] = "member",
        actor_user_id: str | None = None,
    ) -> WorkQueueMember:
        return await self._service.add_queue_member(
            company_id=company_id,
            work_queue_id=work_queue_id,
            member=member,
            role=role,
            actor_user_id=actor_user_id,
        )

    async def remove_queue_member(
        self,
        *,
        work_queue_id: str,
        member: WorkActor,
        actor_user_id: str,
    ) -> bool:
        return await self._service.remove_queue_member(
            work_queue_id=work_queue_id,
            member=member,
            actor_user_id=actor_user_id,
        )

    async def list_boards(
        self, company_id: str, *, namespace: str | None = None
    ) -> list[Board]:
        return await self._service.list_boards(company_id, namespace=namespace)

    async def get_board(self, company_id: str, board_id: str) -> Board:
        return await Board.require_in_company(company_id, board_id)

    async def create_board(
        self,
        *,
        company_id: str,
        name: str,
        columns: list[BoardColumn],
        namespace: str | None = None,
        board_key: str = "generic",
    ) -> Board:
        return await self._service.create_board(
            company_id=company_id,
            name=name,
            columns=columns,
            namespace=namespace,
            board_key=board_key,
        )

    async def update_board(
        self,
        *,
        company_id: str,
        board_id: str,
        name: str | None = None,
        columns: list[BoardColumn] | None = None,
    ) -> Board:
        return await self._service.update_board(
            company_id=company_id,
            board_id=board_id,
            name=name,
            columns=columns,
        )
