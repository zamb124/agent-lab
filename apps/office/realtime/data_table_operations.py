"""DataTable (SQLite FileRecord): один `op_*` на verb для REST и WS RPC.

Байты ходят только через Files API: экспорт создаёт ephemeral `FileRecord`,
импорт читает уже загруженный chunked upload по `upload_file_id`.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Literal, TypeVar, assert_never

from pydantic import Field

from apps.office.di import Di
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
from core.files.create_spec import FileCreateSpec, FilePostCreate, FileSourceKind, FileSourceRef
from core.files.models import FileRecord
from core.files.object_store.principals import SystemPrincipal
from core.files.registry import default_retention_for_source
from core.files.types import ext_to_mime
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


class OfficeDataTableExportPayload(StrictBaseModel):
    file_id: str = Field(min_length=1)
    table_name: str = Field(min_length=1)
    source_format: Literal["csv", "xlsx"]


class OfficeDataTableImportPayload(OfficeDataTableExportPayload):
    upload_file_id: str = Field(min_length=1)


async def _run(awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except DataTableNotFoundError as exc:
        raise_not_found(exc)
    except DataTableLockedError as exc:
        raise_conflict(exc)
    except ValueError as exc:
        raise_invalid(exc)


async def _require_view(di: Di, file_id: str) -> None:
    _ = require_active_company()
    try:
        await di.authz_service.require_can_view(AuthzObject.office_document(file_id))
    except AuthzDenied as exc:
        raise_forbidden(exc)


async def _require_edit(di: Di, file_id: str) -> None:
    _ = require_active_company()
    try:
        await di.authz_service.require_can_edit(AuthzObject.office_document(file_id))
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
    di: Di, record: FileRecord, placement: DocsPlacement, user: User
) -> FileRecord:
    company = require_active_company()
    try:
        _ = await di.docs_placement_service.bind(
            placement,
            company_id=company.company_id,
            user_id=user.user_id,
        )
    except Exception:
        _ = await di.files_service.delete(record.file_id)
        raise
    return record


async def op_data_tables_create(
    payload: DataTableCreateRequest,
    *,
    user: User,
    di: Di,
) -> FileRecord:
    _ = require_active_company()
    namespace = _resolved_namespace(payload.namespace)
    record = await _run(
        di.data_table_service.create(
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
    return await _bind_or_delete(di, record, placement, user)


async def op_data_tables_get(
    payload: OfficeDataTableFileIdPayload,
    *,
    user: User,
    di: Di,
) -> DataTableFileSnapshot:
    _ = user
    await _require_view(di, payload.file_id)
    return await _run(di.data_table_service.snapshot(payload.file_id))


async def op_data_tables_promote(
    payload: OfficeDataTablePromotePayload,
    *,
    user: User,
    di: Di,
) -> FileRecord:
    await _require_edit(di, payload.file_id)
    namespace = _resolved_namespace(None)
    record = await _run(
        di.data_table_service.promote_session_to_asset(
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
    return await _bind_or_delete(di, record, placement, user)


async def op_data_tables_table_create(
    payload: OfficeDataTableCreateTablePayload,
    *,
    user: User,
    di: Di,
) -> DataTableSchemaSnapshot:
    _ = user
    await _require_edit(di, payload.file_id)
    spec = DataTableCreateTableRequest(name=payload.name, columns=payload.columns)
    return await _run(di.data_table_service.create_table(payload.file_id, spec))


async def op_data_tables_column_add(
    payload: OfficeDataTableAddColumnPayload,
    *,
    user: User,
    di: Di,
) -> DataTableSchemaSnapshot:
    _ = user
    await _require_edit(di, payload.file_id)
    spec = DataTableAddColumnRequest(
        name=payload.name, column_type=payload.column_type, not_null=payload.not_null
    )
    return await _run(
        di.data_table_service.add_column(payload.file_id, payload.table_name, spec)
    )


async def op_data_tables_rows_list(
    payload: OfficeDataTableRowsListPayload,
    *,
    user: User,
    di: Di,
) -> CursorPage[DataTableRow]:
    _ = user
    await _require_view(di, payload.file_id)
    return await _run(
        di.data_table_service.page_rows(
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
    di: Di,
) -> DataTableInsertRowsResponse:
    _ = user
    await _require_edit(di, payload.file_id)
    row_ids = await _run(
        di.data_table_service.insert_rows(payload.file_id, payload.table_name, payload.rows)
    )
    return DataTableInsertRowsResponse(row_ids=row_ids)


async def op_data_tables_row_update(
    payload: OfficeDataTableUpdateRowPayload,
    *,
    user: User,
    di: Di,
) -> DataTableUpdateRowResponse:
    _ = user
    await _require_edit(di, payload.file_id)
    await _run(
        di.data_table_service.update_row(
            payload.file_id, payload.table_name, payload.row_id, payload.values
        )
    )
    return DataTableUpdateRowResponse()


async def op_data_tables_rows_delete(
    payload: OfficeDataTableDeleteRowsPayload,
    *,
    user: User,
    di: Di,
) -> DataTableDeleteRowsResponse:
    _ = user
    await _require_edit(di, payload.file_id)
    deleted = await _run(
        di.data_table_service.delete_rows(
            payload.file_id, payload.table_name, payload.row_ids
        )
    )
    return DataTableDeleteRowsResponse(deleted=deleted)


async def op_data_tables_query(
    payload: OfficeDataTableQueryPayload,
    *,
    user: User,
    di: Di,
) -> DataTableQueryResult:
    _ = user
    is_write = payload.sql.strip().lower().startswith(("insert", "update", "delete"))
    if is_write:
        await _require_edit(di, payload.file_id)
    else:
        await _require_view(di, payload.file_id)
    return await _run(di.data_table_service.query(payload.file_id, payload.sql))


async def op_data_tables_export(
    payload: OfficeDataTableExportPayload,
    *,
    user: User,
    di: Di,
) -> FileRecord:
    """Выгрузка таблицы в CSV/XLSX как ephemeral файл; клиент скачивает его по `download_url`."""
    _ = user
    await _require_view(di, payload.file_id)
    exported, filename = await _run(
        di.data_table_service.export_tabular(
            payload.file_id,
            table_name=payload.table_name,
            source_format=payload.source_format,
        )
    )
    spec = FileCreateSpec(
        source_kind=FileSourceKind.GENERATED_EPHEMERAL,
        source_ref=FileSourceRef(),
        retention=default_retention_for_source(FileSourceKind.GENERATED_EPHEMERAL),
        post_create=FilePostCreate(is_public=False),
    )
    return await di.files_service.create(
        spec,
        exported,
        original_name=filename,
        content_type=ext_to_mime(f".{payload.source_format}"),
    )


async def op_data_tables_import(
    payload: OfficeDataTableImportPayload,
    *,
    user: User,
    di: Di,
) -> DataTableSchemaSnapshot:
    """Импорт CSV/XLSX из файла, уже загруженного chunked Files API, в новую таблицу."""
    _ = user
    await _require_edit(di, payload.file_id)
    company_id = require_active_company().company_id
    upload = await di.files_service.get_optional(payload.upload_file_id)
    if upload is None or upload.company_id != company_id:
        raise_not_found(LookupError(f"import file {payload.upload_file_id!r} not found"))
    raw = await di.files_service.read_bytes(
        upload,
        SystemPrincipal(company_id=company_id),
    )
    return await _run(
        di.data_table_service.import_tabular(
            payload.file_id,
            table_name=payload.table_name,
            source_format=payload.source_format,
            raw=raw,
        )
    )
