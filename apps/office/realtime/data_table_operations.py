"""DataTable (SQLite FileRecord): один `op_*` на verb для REST и WS RPC.

Байты остаются REST: экспорт таблицы (`GET .../export`) и импорт (multipart `POST .../import`).
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Literal, TypeVar, assert_never

from pydantic import Field

from apps.office.container import OfficeContainer
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.context import require_active_company, require_context
from core.data_tables.lock import DataTableLockedError
from core.data_tables.models import (
    MAX_PAGE_LIMIT,
    MAX_SEARCH_Q_LENGTH,
    DataTableAddColumnRequest,
    DataTableCreateRequest,
    DataTableCreateTableRequest,
    DataTableDeleteRowsRequest,
    DataTableDeleteRowsResponse,
    DataTableFileSnapshot,
    DataTableInsertRowsRequest,
    DataTableInsertRowsResponse,
    DataTablePromoteRequest,
    DataTableQueryRequest,
    DataTableQueryResult,
    DataTableRow,
    DataTableSchemaSnapshot,
    DataTableScope,
    DataTableUpdateRowRequest,
    DataTableUpdateRowResponse,
)
from core.data_tables.service import DataTableNotFoundError
from core.documents.placement import DocsPlacement, DocsPlacementAnchor
from core.files.models import FileRecord
from core.models.base import StrictBaseModel
from core.models.identity_models import User
from core.pagination import CursorPage
from core.websocket import raise_conflict, raise_forbidden, raise_invalid, raise_not_found

T = TypeVar("T")


class OfficeDataTableFileIdPayload(StrictBaseModel):
    file_id: str = Field(min_length=1)


class OfficeDataTablePromotePayload(DataTablePromoteRequest):
    file_id: str = Field(min_length=1)


class OfficeDataTableCreateTablePayload(DataTableCreateTableRequest):
    file_id: str = Field(min_length=1)


class OfficeDataTableAddColumnPayload(DataTableAddColumnRequest):
    file_id: str = Field(min_length=1)
    table_name: str = Field(min_length=1)


class OfficeDataTableRowsListPayload(StrictBaseModel):
    file_id: str = Field(min_length=1)
    table_name: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=MAX_PAGE_LIMIT)
    cursor: str | None = None
    sort_column: str | None = None
    sort_dir: Literal["asc", "desc"] = "asc"
    filter_column: str | None = None
    filter_value: str | None = None
    q: str | None = Field(default=None, min_length=1, max_length=MAX_SEARCH_Q_LENGTH)
    column_q: list[str] | None = None


class OfficeDataTableInsertRowsPayload(DataTableInsertRowsRequest):
    file_id: str = Field(min_length=1)
    table_name: str = Field(min_length=1)


class OfficeDataTableUpdateRowPayload(DataTableUpdateRowRequest):
    file_id: str = Field(min_length=1)
    table_name: str = Field(min_length=1)
    row_id: int


class OfficeDataTableDeleteRowsPayload(DataTableDeleteRowsRequest):
    file_id: str = Field(min_length=1)
    table_name: str = Field(min_length=1)


class OfficeDataTableQueryPayload(DataTableQueryRequest):
    file_id: str = Field(min_length=1)


async def _run(awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except DataTableNotFoundError as exc:
        raise_not_found(exc)
    except DataTableLockedError as exc:
        raise_conflict(exc)
    except ValueError as exc:
        raise_invalid(exc)


async def _require_view(container: OfficeContainer, file_id: str) -> None:
    _ = require_active_company()
    try:
        await container.authz_service.require_can_view(AuthzObject.office_document(file_id))
    except AuthzDenied as exc:
        raise_forbidden(exc)


async def _require_edit(container: OfficeContainer, file_id: str) -> None:
    _ = require_active_company()
    try:
        await container.authz_service.require_can_edit(AuthzObject.office_document(file_id))
    except AuthzDenied as exc:
        raise_forbidden(exc)


def _resolved_namespace(explicit: str | None) -> str:
    if explicit is not None and explicit.strip() != "":
        return explicit.strip()
    active = require_context().active_namespace.strip()
    if active != "":
        return active
    raise_invalid(ValueError("namespace is required"))


def _placement_anchor(
    scope: DataTableScope,
    *,
    flow_id: str | None,
    session_id: str | None,
) -> DocsPlacementAnchor:
    if scope == "office_document":
        return DocsPlacementAnchor(source_kind="office_manual")
    if scope == "flow_asset":
        return DocsPlacementAnchor(source_kind="flow_asset", flow_id=flow_id, session_id=session_id)
    if scope == "flow_session":
        return DocsPlacementAnchor(
            source_kind="flow_session",
            flow_id=flow_id,
            session_id=session_id,
        )
    assert_never(scope)


def _data_table_placement(
    *,
    file_id: str,
    title: str,
    scope: DataTableScope,
    namespace: str,
    flow_id: str | None,
    session_id: str | None,
) -> DocsPlacement:
    path_segments: list[str] | None = ["Tables"] if scope == "office_document" else None
    return DocsPlacement(
        namespace=namespace,
        file_id=file_id,
        title=title,
        path_segments=path_segments,
        anchor=_placement_anchor(scope, flow_id=flow_id, session_id=session_id),
    )


async def _bind_or_delete(
    container: OfficeContainer, record: FileRecord, placement: DocsPlacement, user: User
) -> FileRecord:
    company = require_active_company()
    try:
        _ = await container.docs_placement_service.bind(
            placement,
            company_id=company.company_id,
            user_id=user.user_id,
        )
    except Exception:
        _ = await container.files_service.delete(record.file_id)
        raise
    return record


async def op_data_tables_create(
    payload: DataTableCreateRequest,
    *,
    user: User,
    container: OfficeContainer,
) -> FileRecord:
    _ = require_active_company()
    namespace = _resolved_namespace(payload.namespace)
    record = await _run(
        container.data_table_service.create(
            original_name=payload.original_name,
            scope=payload.scope,
            flow_id=payload.flow_id,
            session_id=payload.session_id,
            tables=payload.tables,
            namespace=namespace,
        )
    )
    placement = _data_table_placement(
        file_id=record.file_id,
        title=record.original_name,
        scope=payload.scope,
        namespace=namespace,
        flow_id=payload.flow_id,
        session_id=payload.session_id,
    )
    return await _bind_or_delete(container, record, placement, user)


async def op_data_tables_get(
    payload: OfficeDataTableFileIdPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> DataTableFileSnapshot:
    _ = user
    await _require_view(container, payload.file_id)
    return await _run(container.data_table_service.snapshot(payload.file_id))


async def op_data_tables_promote(
    payload: OfficeDataTablePromotePayload,
    *,
    user: User,
    container: OfficeContainer,
) -> FileRecord:
    await _require_edit(container, payload.file_id)
    namespace = _resolved_namespace(None)
    record = await _run(
        container.data_table_service.promote_session_to_asset(
            payload.file_id,
            flow_id=payload.flow_id,
            original_name=payload.original_name,
        )
    )
    placement = _data_table_placement(
        file_id=record.file_id,
        title=record.original_name,
        scope="flow_asset",
        namespace=namespace,
        flow_id=payload.flow_id,
        session_id=None,
    )
    return await _bind_or_delete(container, record, placement, user)


async def op_data_tables_table_create(
    payload: OfficeDataTableCreateTablePayload,
    *,
    user: User,
    container: OfficeContainer,
) -> DataTableSchemaSnapshot:
    _ = user
    await _require_edit(container, payload.file_id)
    spec = DataTableCreateTableRequest(name=payload.name, columns=payload.columns)
    return await _run(container.data_table_service.create_table(payload.file_id, spec))


async def op_data_tables_column_add(
    payload: OfficeDataTableAddColumnPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> DataTableSchemaSnapshot:
    _ = user
    await _require_edit(container, payload.file_id)
    spec = DataTableAddColumnRequest(
        name=payload.name, column_type=payload.column_type, not_null=payload.not_null
    )
    return await _run(
        container.data_table_service.add_column(payload.file_id, payload.table_name, spec)
    )


async def op_data_tables_rows_list(
    payload: OfficeDataTableRowsListPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> CursorPage[DataTableRow]:
    _ = user
    await _require_view(container, payload.file_id)
    return await _run(
        container.data_table_service.page_rows(
            payload.file_id,
            payload.table_name,
            limit=payload.limit,
            cursor=payload.cursor,
            sort_column=payload.sort_column,
            sort_dir=payload.sort_dir,
            filter_column=payload.filter_column,
            filter_value=payload.filter_value,
            q=payload.q,
            column_q=payload.column_q,
        )
    )


async def op_data_tables_rows_insert(
    payload: OfficeDataTableInsertRowsPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> DataTableInsertRowsResponse:
    _ = user
    await _require_edit(container, payload.file_id)
    row_ids = await _run(
        container.data_table_service.insert_rows(payload.file_id, payload.table_name, payload.rows)
    )
    return DataTableInsertRowsResponse(row_ids=row_ids)


async def op_data_tables_row_update(
    payload: OfficeDataTableUpdateRowPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> DataTableUpdateRowResponse:
    _ = user
    await _require_edit(container, payload.file_id)
    await _run(
        container.data_table_service.update_row(
            payload.file_id, payload.table_name, payload.row_id, payload.values
        )
    )
    return DataTableUpdateRowResponse()


async def op_data_tables_rows_delete(
    payload: OfficeDataTableDeleteRowsPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> DataTableDeleteRowsResponse:
    _ = user
    await _require_edit(container, payload.file_id)
    deleted = await _run(
        container.data_table_service.delete_rows(
            payload.file_id, payload.table_name, payload.row_ids
        )
    )
    return DataTableDeleteRowsResponse(deleted=deleted)


async def op_data_tables_query(
    payload: OfficeDataTableQueryPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> DataTableQueryResult:
    _ = user
    is_write = payload.sql.strip().lower().startswith(("insert", "update", "delete"))
    if is_write:
        await _require_edit(container, payload.file_id)
    else:
        await _require_view(container, payload.file_id)
    return await _run(container.data_table_service.query(payload.file_id, payload.sql))
