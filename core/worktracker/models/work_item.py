"""Таблица worktracker."""

from __future__ import annotations

import json
from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, execute_raw

from core.files.file_ref import FileRef
from core.identity.flow_employee import flow_employee_user_id
from core.models.platform_model import PlatformModel
from core.types import JsonValue, parse_json_object, require_json_object
from core.variables.models import VariableMap
from core.worktracker.models.types import (
    TERMINAL_WORK_ITEM_STATES,
    AssigneeKind,
    CalendarEventLink,
    CrmEntityLink,
    FileLink,
    FlowSessionLink,
    QueueAssignment,
    RagDocumentLink,
    ShopLink,
    StockLocationLink,
    StockTransferLink,
    SyncMessageLink,
    SystemActor,
    UnassignedAssignment,
    UserActor,
    UsersAssignment,
    WorkItemConversationRef,
    WorkItemHook,
    WorkItemHookEvent,
    WorkItemInteractionMode,
    WorkItemInteractionPolicy,
    WorkItemInteractionSpec,
    WorkItemKind,
    WorkItemLinkKind,
    WorkItemPriority,
    WorkItemResolution,
    WorkItemState,
    WorkItemToWorkItemLink,
)


class WorkItem(PlatformModel):
    """Каноническая единица работы. Таблица ``work_items``."""

    __database_alias__: ClassVar[str | None] = "worktracker"
    __global_model__: ClassVar[bool] = True

    work_item_id: str = DbField(db_pk=True, max_length=64, min_length=1)
    company_id: str = DbField(max_length=100, min_length=1, db_index=True)
    title: str = DbField(min_length=1, db_type="TEXT")
    created_by: UserActor | SystemActor = DbField(db_type="JSONB", discriminator="actor_kind")
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    namespace: str | None = DbField(default=None, max_length=100)
    description: str = DbField(default="", db_type="TEXT")
    kind: WorkItemKind = DbField(default=WorkItemKind.GENERIC, max_length=32, db_type="TEXT")
    state: WorkItemState = DbField(default=WorkItemState.OPEN, max_length=32, db_index=True, db_type="TEXT")
    board_id: str | None = DbField(default=None, max_length=64)
    board_column_id: str | None = DbField(default=None, max_length=64)
    priority: WorkItemPriority = DbField(default=WorkItemPriority.NORMAL, max_length=16, db_type="TEXT")
    due_date: datetime | None = DbField(default=None)
    labels: list[str] = DbField(default_factory=list, db_type="JSONB")
    assignment: UnassignedAssignment | UsersAssignment | QueueAssignment = DbField(
        default_factory=UnassignedAssignment,
        db_type="JSONB",
        discriminator="assignee_kind",
    )
    blocking: bool = DbField(default=False)
    interaction: WorkItemInteractionSpec | None = DbField(default=None, db_type="JSONB")
    hooks: list[WorkItemHook] = DbField(default_factory=list, db_type="JSONB")
    resolution: WorkItemResolution | None = DbField(default=None, db_type="JSONB")
    links: list[
        CrmEntityLink
        | FlowSessionLink
        | SyncMessageLink
        | RagDocumentLink
        | FileLink
        | CalendarEventLink
        | StockTransferLink
        | StockLocationLink
        | ShopLink
        | WorkItemToWorkItemLink
    ] = DbField(default_factory=list, db_type="JSONB")
    variables: VariableMap = DbField(default_factory=dict, db_type="JSONB")
    attachments: list[FileRef] = DbField(default_factory=list, db_type="JSONB")
    interaction_policy: WorkItemInteractionPolicy | None = None

    class Meta:
        is_table: bool = True
        table_name: str = "work_items"
        indexes: list[Index] = [
            Index(["company_id", "state"]),
            Index(["company_id", "board_id"]),
            Index(["company_id", "namespace"]),
        ]

    def hooks_for(self, event: WorkItemHookEvent) -> list[WorkItemHook]:
        return [hook for hook in self.hooks if hook.event == event]

    def flow_session_link(self) -> FlowSessionLink | None:
        for link in self.links:
            if isinstance(link, FlowSessionLink):
                return link
        return None

    @classmethod
    async def require_in_company(cls, company_id: str, work_item_id: str) -> Self:
        item = await cls.objects.filter(
            company_id=company_id,
            work_item_id=work_item_id,
        ).get_or_none()
        if item is None:
            raise ValueError(f"WorkItem {work_item_id!r} not found")
        return item

    @classmethod
    async def delete_in_company(cls, company_id: str, work_item_id: str) -> bool:
        if company_id == "":
            raise ValueError("company_id cannot be empty.")
        if work_item_id == "":
            raise ValueError("work_item_id cannot be empty.")
        deleted = await cls.objects.filter(
            company_id=company_id,
            work_item_id=work_item_id,
        ).delete()
        return deleted > 0

    @classmethod
    async def create(cls, item: Self) -> Self:
        return await cls.objects.create(instance=item)

    @classmethod
    async def list_created_desc(
        cls,
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
        """Окно задач компании, ORDER BY created_at DESC. None в фильтрах не сужает. Пустой work_queue_ids даёт пустой список. limit по умолчанию 200."""
        sql = work_item_sql(
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
        sql.params.append(limit)
        limit_placeholder = f"${len(sql.params)}"
        sql.params.append(offset)
        offset_placeholder = f"${len(sql.params)}"
        query = (
            "SELECT row_to_json(work_items) AS item FROM work_items "
            + f"WHERE {sql.where()} ORDER BY created_at DESC "
            + f"LIMIT {limit_placeholder} OFFSET {offset_placeholder}"
        )
        rows = await execute_raw(query, sql.params, using="worktracker")
        return [_work_item_from_row(row) for row in rows]

    @classmethod
    async def count_for_filters(
        cls,
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
        """Число задач компании с теми же фильтрами, что у list_created_desc, без окна. None не сужает. Пустой work_queue_ids — 0."""
        sql = work_item_sql(
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
        rows = await execute_raw(
            f"SELECT count(*)::int AS total FROM work_items WHERE {sql.where()}",
            sql.params,
            using="worktracker",
        )
        total = require_json_object(rows[0], "work_item_count")["total"]
        if isinstance(total, bool) or not isinstance(total, int):
            raise TypeError("work_item count must be int")
        return total

    @classmethod
    async def list_open_for_shop_by_created_at_desc(
        cls, company_id: str, shop_id: str, *, limit: int = 50
    ) -> list[WorkItem]:
        """Нетерминальные задачи компании с ShopLink(shop_id), ORDER BY created_at DESC, не больше limit."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        sql = work_item_sql(
            company_id,
            board_id=None,
            namespace=None,
            kind=None,
            state=None,
            work_queue_id=None,
            assignee_user_id=None,
            assignee_flow_id=None,
            exclude_terminal=True,
            queue_unclaimed_only=False,
            work_queue_ids=None,
        )
        link_json = sql.add(
            json.dumps([{"link_kind": WorkItemLinkKind.SHOP.value, "shop_id": shop_id}])
        )
        sql.clauses.append(f"links @> {link_json}::jsonb")
        sql.params.append(limit)
        query = (
            "SELECT row_to_json(work_items) AS item FROM work_items "
            + f"WHERE {sql.where()} ORDER BY created_at DESC LIMIT ${len(sql.params)}"
        )
        rows = await execute_raw(query, sql.params, using="worktracker")
        return [_work_item_from_row(row) for row in rows]

    @classmethod
    async def any_by_correlation_id(
        cls, company_id: str, correlation_id: str
    ) -> Self | None:
        """Любая задача компании, у которой hooks[].binding.correlation_id совпал. Порядок строк не задан. Нет совпадения — None."""
        rows = await cls.objects.filter(company_id=company_id).all()
        for row in rows:
            for hook in row.hooks:
                if hook.binding.get("correlation_id") == correlation_id:
                    return row
        return None

    @classmethod
    async def any_crm_activity_by_entity_id(
        cls, company_id: str, entity_id: str
    ) -> Self | None:
        """Любая задача kind=crm_activity, у которой CrmEntityLink.entity_id совпал. Порядок строк не задан. Нет совпадения — None."""
        rows = await cls.objects.filter(
            company_id=company_id,
            kind=WorkItemKind.CRM_ACTIVITY,
        ).all()
        for row in rows:
            for link in row.links:
                if isinstance(link, CrmEntityLink) and link.entity_id == entity_id:
                    return row
        return None

    @classmethod
    async def ids_by_crm_entity_id(
        cls, company_id: str, entity_ids: list[str]
    ) -> dict[str, str]:
        """entity_id к work_item_id среди crm_activity. Пустой список — {}. Нет связи — ключа нет. Порядок строк не задан, повторный entity_id перезаписывает значение."""
        if len(entity_ids) == 0:
            return {}
        wanted = set(entity_ids)
        mapped: dict[str, str] = {}
        rows = await cls.objects.filter(
            company_id=company_id,
            kind=WorkItemKind.CRM_ACTIVITY,
        ).all()
        for row in rows:
            for link in row.links:
                if isinstance(link, CrmEntityLink) and link.entity_id in wanted:
                    mapped[link.entity_id] = row.work_item_id
        return mapped


class _WorkItemSql:
    def __init__(self, company_id: str) -> None:
        self.clauses: list[str] = ["company_id = $1"]
        self.params: list[str | int] = [company_id]

    def add(self, value: str) -> str:
        self.params.append(value)
        return f"${len(self.params)}"

    def where(self) -> str:
        return " AND ".join(self.clauses)


def work_item_sql(
    company_id: str,
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
    work_queue_ids: list[str] | None,
) -> _WorkItemSql:
    sql = _WorkItemSql(company_id)
    if board_id is not None:
        sql.clauses.append(f"board_id = {sql.add(board_id)}")
    if namespace is not None:
        sql.clauses.append(f"namespace = {sql.add(namespace)}")
    if kind is not None:
        sql.clauses.append(f"kind = {sql.add(kind.value)}")
    if state is not None:
        sql.clauses.append(f"state = {sql.add(state.value)}")
    if exclude_terminal:
        placeholders = [sql.add(item.value) for item in TERMINAL_WORK_ITEM_STATES]
        sql.clauses.append(f"state NOT IN ({', '.join(placeholders)})")
    if work_queue_id is not None:
        sql.clauses.append(
            f"assignment->>'assignee_kind' = {sql.add(AssigneeKind.QUEUE.value)}"
        )
        sql.clauses.append(f"assignment->>'work_queue_id' = {sql.add(work_queue_id)}")
    if assignee_flow_id is not None:
        sql.clauses.append(
            f"assignment->>'assignee_kind' = {sql.add(AssigneeKind.USERS.value)}"
        )
        user_ids_json = sql.add(json.dumps([flow_employee_user_id(assignee_flow_id)]))
        sql.clauses.append(f"assignment->'user_ids' @> {user_ids_json}::jsonb")
    if assignee_user_id is not None:
        sql.clauses.append(
            f"assignment->>'assignee_kind' = {sql.add(AssigneeKind.USERS.value)}"
        )
        sql.clauses.append(
            f"assignment->'user_ids' @> {sql.add(json.dumps([assignee_user_id]))}::jsonb"
        )
    if queue_unclaimed_only:
        sql.clauses.append(
            f"assignment->>'assignee_kind' = {sql.add(AssigneeKind.QUEUE.value)}"
        )
        sql.clauses.append("assignment->>'claimed_by_user_id' IS NULL")
    if work_queue_ids is not None:
        if len(work_queue_ids) == 0:
            sql.clauses.append("FALSE")
        else:
            placeholders = ", ".join(sql.add(queue_id) for queue_id in work_queue_ids)
            sql.clauses.append(
                f"assignment->>'assignee_kind' = {sql.add(AssigneeKind.QUEUE.value)}"
            )
            sql.clauses.append(f"assignment->>'work_queue_id' IN ({placeholders})")
            sql.clauses.append("assignment->>'claimed_by_user_id' IS NULL")
    return sql


def _work_item_from_row(row: JsonValue) -> WorkItem:
    parsed = require_json_object(row, "work_item")
    raw_item = parsed["item"]
    if isinstance(raw_item, str):
        payload = parse_json_object(raw_item, "work_item")
    else:
        payload = require_json_object(raw_item, "work_item")
    return WorkItem.model_validate(payload)


def build_conversation_ref(item: WorkItem) -> WorkItemConversationRef | None:
    """Строит ссылку на разговор из типизированного FlowSessionLink задачи."""
    link = item.flow_session_link()
    if link is None:
        return None
    if link.context_id is None or link.flow_id is None:
        return None
    return WorkItemConversationRef(
        session_id=link.session_id,
        context_id=link.context_id,
        flow_id=link.flow_id,
        branch_id=link.branch_id or "default",
        a2a_task_id=link.a2a_task_id,
    )


def build_interaction_policy(
    item: WorkItem,
    *,
    operator_authorized: bool,
) -> WorkItemInteractionPolicy:
    """Вычисляет политику композера карточки задачи.

    Оба HITL-режима: composer доступен, если оператор авторизован и задача не terminal.
    single_reply: Submit = complete + closing reply (лейбл «Ответить и завершить»).
    takeover: Submit = ask; отдельная кнопка Complete.
    Прочее: mode=none (обычная задача, встроенного чата нет).
    """
    spec = item.interaction
    if spec is None or spec.mode == WorkItemInteractionMode.NONE:
        return WorkItemInteractionPolicy(mode=WorkItemInteractionMode.NONE)
    is_terminal = item.state in TERMINAL_WORK_ITEM_STATES
    active = operator_authorized and not is_terminal
    return WorkItemInteractionPolicy(
        mode=spec.mode,
        can_send=active,
        can_complete=active,
        conversation=build_conversation_ref(item),
    )
