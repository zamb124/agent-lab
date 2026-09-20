"""HTTP API DataTable: тонкое REST-зеркало `op_data_tables_*`; байты (export/import) остаются REST."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from apps.office.dependencies import ContainerDep
from apps.office.realtime.data_table_operations import (
    OfficeDataTableAddColumnPayload,
    OfficeDataTableCreateTablePayload,
    OfficeDataTableDeleteRowsPayload,
    OfficeDataTableFileIdPayload,
    OfficeDataTableInsertRowsPayload,
    OfficeDataTablePromotePayload,
    OfficeDataTableQueryPayload,
    OfficeDataTableRowsListPayload,
    OfficeDataTableUpdateRowPayload,
    op_data_tables_column_add,
    op_data_tables_create,
    op_data_tables_get,
    op_data_tables_promote,
    op_data_tables_query,
    op_data_tables_row_update,
    op_data_tables_rows_delete,
    op_data_tables_rows_insert,
    op_data_tables_rows_list,
    op_data_tables_table_create,
)
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
    DataTableUpdateRowRequest,
    DataTableUpdateRowResponse,
)
from core.data_tables.service import DataTableNotFoundError
from core.files.models import FileRecord
from core.files.types import ext_to_mime
from core.pagination import CursorPage

router = APIRouter(tags=["data-tables"])


def _http_from_data_table_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DataTableNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, DataTableLockedError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


async def _require_view(container: ContainerDep, file_id: str) -> None:
    _ = require_active_company()
    await container.authz_service.require_can_view(AuthzObject.office_document(file_id))


async def _require_edit(container: ContainerDep, file_id: str) -> None:
    _ = require_active_company()
    await container.authz_service.require_can_edit(AuthzObject.office_document(file_id))


@router.post("/data-tables", response_model=FileRecord)
async def create_data_table(
    body: DataTableCreateRequest,
    container: ContainerDep,
) -> FileRecord:
    return await op_data_tables_create(body, user=require_context().user, container=container)


@router.get("/data-tables/{file_id}", response_model=DataTableFileSnapshot)
async def get_data_table(
    file_id: str,
    container: ContainerDep,
) -> DataTableFileSnapshot:
    return await op_data_tables_get(
        OfficeDataTableFileIdPayload(file_id=file_id),
        user=require_context().user,
        container=container,
    )


@router.post("/data-tables/{file_id}/promote", response_model=FileRecord)
async def promote_data_table(
    file_id: str,
    body: DataTablePromoteRequest,
    container: ContainerDep,
) -> FileRecord:
    return await op_data_tables_promote(
        OfficeDataTablePromotePayload(
            file_id=file_id, flow_id=body.flow_id, original_name=body.original_name
        ),
        user=require_context().user,
        container=container,
    )


@router.post("/data-tables/{file_id}/tables", response_model=DataTableSchemaSnapshot)
async def create_data_table_table(
    file_id: str,
    body: DataTableCreateTableRequest,
    container: ContainerDep,
) -> DataTableSchemaSnapshot:
    return await op_data_tables_table_create(
        OfficeDataTableCreateTablePayload(file_id=file_id, name=body.name, columns=body.columns),
        user=require_context().user,
        container=container,
    )


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
    return await op_data_tables_column_add(
        OfficeDataTableAddColumnPayload(
            file_id=file_id,
            table_name=table_name,
            name=body.name,
            column_type=body.column_type,
            not_null=body.not_null,
        ),
        user=require_context().user,
        container=container,
    )


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
    return await op_data_tables_rows_list(
        OfficeDataTableRowsListPayload(
            file_id=file_id,
            table_name=table_name,
            limit=limit,
            cursor=cursor,
            sort_column=sort_column,
            sort_dir=sort_dir,
            filter_column=filter_column,
            filter_value=filter_value,
            q=q,
            column_q=column_q,
        ),
        user=require_context().user,
        container=container,
    )


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
    return await op_data_tables_rows_insert(
        OfficeDataTableInsertRowsPayload(file_id=file_id, table_name=table_name, rows=body.rows),
        user=require_context().user,
        container=container,
    )


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
    return await op_data_tables_row_update(
        OfficeDataTableUpdateRowPayload(
            file_id=file_id, table_name=table_name, row_id=row_id, values=body.values
        ),
        user=require_context().user,
        container=container,
    )


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
    return await op_data_tables_rows_delete(
        OfficeDataTableDeleteRowsPayload(
            file_id=file_id, table_name=table_name, row_ids=body.row_ids
        ),
        user=require_context().user,
        container=container,
    )


@router.post("/data-tables/{file_id}/query", response_model=DataTableQueryResult)
async def query_data_table(
    file_id: str,
    body: DataTableQueryRequest,
    container: ContainerDep,
) -> DataTableQueryResult:
    return await op_data_tables_query(
        OfficeDataTableQueryPayload(file_id=file_id, sql=body.sql),
        user=require_context().user,
        container=container,
    )


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
