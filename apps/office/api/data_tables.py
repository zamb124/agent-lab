"""HTTP API DataTable: SQLite FileRecord, paging и мутации через DataTableService."""

from __future__ import annotations

from typing import Annotated, Literal, assert_never

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from apps.office.dependencies import ContainerDep
from core.authz.models import AuthzObject
from core.context import get_context
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
from core.files.types import ext_to_mime
from core.models.identity_models import Company, User
from core.pagination import CursorPage

router = APIRouter(tags=["data-tables"])


def _require_user() -> tuple[Company, User, str | None]:
    ctx = get_context()
    if ctx is None:
        raise HTTPException(status_code=403, detail="Контекст запроса не установлен")
    if ctx.active_company is None:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    return ctx.active_company, ctx.user, ctx.active_namespace


def _http_from_data_table_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DataTableNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, DataTableLockedError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


async def _require_view(container: ContainerDep, file_id: str) -> None:
    _ = _require_user()
    await container.authz_service.require_can_view(AuthzObject.office_document(file_id))


async def _require_edit(container: ContainerDep, file_id: str) -> None:
    _ = _require_user()
    await container.authz_service.require_can_edit(AuthzObject.office_document(file_id))


def _resolved_namespace(explicit: str | None, active: str | None) -> str:
    if explicit is not None and explicit.strip() != "":
        return explicit.strip()
    if active is not None and active.strip() != "":
        return active.strip()
    raise HTTPException(status_code=400, detail="namespace is required")


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


@router.post("/data-tables", response_model=FileRecord)
async def create_data_table(
    body: DataTableCreateRequest,
    container: ContainerDep,
) -> FileRecord:
    company, user, active_namespace = _require_user()
    scope = body.scope
    namespace = _resolved_namespace(body.namespace, active_namespace)
    try:
        record = await container.data_table_service.create(
            original_name=body.original_name,
            scope=scope,
            flow_id=body.flow_id,
            session_id=body.session_id,
            tables=body.tables,
            namespace=namespace,
        )
    except (DataTableNotFoundError, DataTableLockedError, ValueError) as exc:
        raise _http_from_data_table_error(exc) from exc
    placement = _data_table_placement(
        file_id=record.file_id,
        title=record.original_name,
        scope=scope,
        namespace=namespace,
        flow_id=body.flow_id,
        session_id=body.session_id,
    )
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


@router.get("/data-tables/{file_id}", response_model=DataTableFileSnapshot)
async def get_data_table(
    file_id: str,
    container: ContainerDep,
) -> DataTableFileSnapshot:
    await _require_view(container, file_id)
    try:
        return await container.data_table_service.snapshot(file_id)
    except (DataTableNotFoundError, DataTableLockedError, ValueError) as exc:
        raise _http_from_data_table_error(exc) from exc


@router.post("/data-tables/{file_id}/promote", response_model=FileRecord)
async def promote_data_table(
    file_id: str,
    body: DataTablePromoteRequest,
    container: ContainerDep,
) -> FileRecord:
    company, user, active_namespace = _require_user()
    await container.authz_service.require_can_edit(AuthzObject.office_document(file_id))
    namespace = _resolved_namespace(None, active_namespace)
    try:
        record = await container.data_table_service.promote_session_to_asset(
            file_id,
            flow_id=body.flow_id,
            original_name=body.original_name,
        )
    except (DataTableNotFoundError, DataTableLockedError, ValueError) as exc:
        raise _http_from_data_table_error(exc) from exc
    placement = _data_table_placement(
        file_id=record.file_id,
        title=record.original_name,
        scope="flow_asset",
        namespace=namespace,
        flow_id=body.flow_id,
        session_id=None,
    )
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


@router.post("/data-tables/{file_id}/tables", response_model=DataTableSchemaSnapshot)
async def create_data_table_table(
    file_id: str,
    body: DataTableCreateTableRequest,
    container: ContainerDep,
) -> DataTableSchemaSnapshot:
    await _require_edit(container, file_id)
    try:
        return await container.data_table_service.create_table(file_id, body)
    except (DataTableNotFoundError, DataTableLockedError, ValueError) as exc:
        raise _http_from_data_table_error(exc) from exc


@router.post(
    "/data-tables/{file_id}/tables/{table_name}/columns",
    response_model=DataTableSchemaSnapshot,
)
async def add_data_table_column(
    file_id: str,
    table_name: str,
    body: DataTableAddColumnRequest,
    container: ContainerDep,
) -> DataTableSchemaSnapshot:
    await _require_edit(container, file_id)
    try:
        return await container.data_table_service.add_column(file_id, table_name, body)
    except (DataTableNotFoundError, DataTableLockedError, ValueError) as exc:
        raise _http_from_data_table_error(exc) from exc


@router.get(
    "/data-tables/{file_id}/tables/{table_name}/rows",
    response_model=CursorPage[DataTableRow],
)
async def list_data_table_rows(
    file_id: str,
    table_name: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = 50,
    cursor: Annotated[str | None, Query()] = None,
    sort_column: Annotated[str | None, Query()] = None,
    sort_dir: Annotated[Literal["asc", "desc"], Query()] = "asc",
    filter_column: Annotated[str | None, Query()] = None,
    filter_value: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query(min_length=1, max_length=MAX_SEARCH_Q_LENGTH)] = None,
    column_q: Annotated[list[str] | None, Query()] = None,
) -> CursorPage[DataTableRow]:
    await _require_view(container, file_id)
    try:
        return await container.data_table_service.page_rows(
            file_id,
            table_name,
            limit=limit,
            cursor=cursor,
            sort_column=sort_column,
            sort_dir=sort_dir,
            filter_column=filter_column,
            filter_value=filter_value,
            q=q,
            column_q=column_q,
        )
    except (DataTableNotFoundError, DataTableLockedError, ValueError) as exc:
        raise _http_from_data_table_error(exc) from exc


@router.get("/data-tables/{file_id}/tables/{table_name}/export")
async def export_data_table_table(
    file_id: str,
    table_name: str,
    container: ContainerDep,
    source_format: Annotated[Literal["csv", "xlsx"], Query(alias="format")],
) -> Response:
    await _require_view(container, file_id)
    try:
        payload, filename = await container.data_table_service.export_tabular(
            file_id,
            table_name=table_name,
            source_format=source_format,
        )
    except (DataTableNotFoundError, DataTableLockedError, ValueError) as exc:
        raise _http_from_data_table_error(exc) from exc
    media_type = ext_to_mime(f".{source_format}")
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/data-tables/{file_id}/tables/{table_name}/rows",
    response_model=DataTableInsertRowsResponse,
)
async def insert_data_table_rows(
    file_id: str,
    table_name: str,
    body: DataTableInsertRowsRequest,
    container: ContainerDep,
) -> DataTableInsertRowsResponse:
    await _require_edit(container, file_id)
    try:
        row_ids = await container.data_table_service.insert_rows(
            file_id, table_name, body.rows
        )
    except (DataTableNotFoundError, DataTableLockedError, ValueError) as exc:
        raise _http_from_data_table_error(exc) from exc
    return DataTableInsertRowsResponse(row_ids=row_ids)


@router.patch(
    "/data-tables/{file_id}/tables/{table_name}/rows/{row_id}",
    response_model=DataTableUpdateRowResponse,
)
async def update_data_table_row(
    file_id: str,
    table_name: str,
    row_id: int,
    body: DataTableUpdateRowRequest,
    container: ContainerDep,
) -> DataTableUpdateRowResponse:
    await _require_edit(container, file_id)
    try:
        await container.data_table_service.update_row(
            file_id, table_name, row_id, body.values
        )
    except (DataTableNotFoundError, DataTableLockedError, ValueError) as exc:
        raise _http_from_data_table_error(exc) from exc
    return DataTableUpdateRowResponse()


@router.post(
    "/data-tables/{file_id}/tables/{table_name}/rows/delete",
    response_model=DataTableDeleteRowsResponse,
)
async def delete_data_table_rows(
    file_id: str,
    table_name: str,
    body: DataTableDeleteRowsRequest,
    container: ContainerDep,
) -> DataTableDeleteRowsResponse:
    await _require_edit(container, file_id)
    try:
        deleted = await container.data_table_service.delete_rows(
            file_id, table_name, body.row_ids
        )
    except (DataTableNotFoundError, DataTableLockedError, ValueError) as exc:
        raise _http_from_data_table_error(exc) from exc
    return DataTableDeleteRowsResponse(deleted=deleted)


@router.post("/data-tables/{file_id}/query", response_model=DataTableQueryResult)
async def query_data_table(
    file_id: str,
    body: DataTableQueryRequest,
    container: ContainerDep,
) -> DataTableQueryResult:
    stripped = body.sql.strip().lower()
    is_write = stripped.startswith(("insert", "update", "delete"))
    if is_write:
        await _require_edit(container, file_id)
    else:
        await _require_view(container, file_id)
    try:
        return await container.data_table_service.query(file_id, body.sql)
    except (DataTableNotFoundError, DataTableLockedError, ValueError) as exc:
        raise _http_from_data_table_error(exc) from exc


@router.post(
    "/data-tables/{file_id}/import",
    response_model=DataTableSchemaSnapshot,
)
async def import_data_table_tabular(
    file_id: str,
    table_name: str,
    source_format: Literal["csv", "xlsx"],
    container: ContainerDep,
    upload: Annotated[UploadFile, File()],
) -> DataTableSchemaSnapshot:
    await _require_edit(container, file_id)
    raw = await upload.read()
    try:
        return await container.data_table_service.import_tabular(
            file_id,
            table_name=table_name,
            source_format=source_format,
            raw=raw,
        )
    except (DataTableNotFoundError, DataTableLockedError, ValueError) as exc:
        raise _http_from_data_table_error(exc) from exc
