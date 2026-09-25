"""HTTP API DataTable: тонкое REST-зеркало `op_data_tables_*`."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from apps.office.di import Di
from apps.office.realtime.data_table_operations import (
    OfficeDataTableAddColumnPayload,
    OfficeDataTableCreateTablePayload,
    OfficeDataTableDeleteRowsPayload,
    OfficeDataTableExportPayload,
    OfficeDataTableFileIdPayload,
    OfficeDataTableImportPayload,
    OfficeDataTableInsertRowsPayload,
    OfficeDataTablePromotePayload,
    OfficeDataTableQueryPayload,
    OfficeDataTableRowsListPayload,
    OfficeDataTableUpdateRowPayload,
    op_data_tables_column_add,
    op_data_tables_create,
    op_data_tables_export,
    op_data_tables_get,
    op_data_tables_import,
    op_data_tables_promote,
    op_data_tables_query,
    op_data_tables_row_update,
    op_data_tables_rows_delete,
    op_data_tables_rows_insert,
    op_data_tables_rows_list,
    op_data_tables_table_create,
)
from core.context import require_context
from core.data_tables.models import (
    MAX_PAGE_LIMIT,
    MAX_SEARCH_Q_LENGTH,
    DataTableAddColumnRequest,
    DataTableCreateRequest,
    DataTableCreateTableRequest,
    DataTableDeleteRowsRequest,
    DataTableDeleteRowsResponse,
    DataTableFileSnapshot,
    DataTableImportRequest,
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
from core.files.models import FileRecord
from core.pagination import CursorPage

router = APIRouter(tags=["data-tables"])


@router.post("/data-tables", response_model=FileRecord)
async def create_data_table(
    body: DataTableCreateRequest,
    di: Di,
) -> FileRecord:
    return await op_data_tables_create(body, user=require_context().user, di=di)


@router.get("/data-tables/{file_id}", response_model=DataTableFileSnapshot)
async def get_data_table(
    file_id: str,
    di: Di,
) -> DataTableFileSnapshot:
    return await op_data_tables_get(
        OfficeDataTableFileIdPayload(file_id=file_id),
        user=require_context().user,
        di=di,
    )


@router.post("/data-tables/{file_id}/promote", response_model=FileRecord)
async def promote_data_table(
    file_id: str,
    body: DataTablePromoteRequest,
    di: Di,
) -> FileRecord:
    return await op_data_tables_promote(
        OfficeDataTablePromotePayload(
            file_id=file_id, flow_id=body.flow_id, original_name=body.original_name
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/data-tables/{file_id}/tables", response_model=DataTableSchemaSnapshot)
async def create_data_table_table(
    file_id: str,
    body: DataTableCreateTableRequest,
    di: Di,
) -> DataTableSchemaSnapshot:
    return await op_data_tables_table_create(
        OfficeDataTableCreateTablePayload(file_id=file_id, name=body.name, columns=body.columns),
        user=require_context().user,
        di=di,
    )


@router.post(
    "/data-tables/{file_id}/tables/{table_name}/columns",
    response_model=DataTableSchemaSnapshot,
)
async def add_data_table_column(
    file_id: str,
    table_name: str,
    body: DataTableAddColumnRequest,
    di: Di,
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
        di=di,
    )


@router.get(
    "/data-tables/{file_id}/tables/{table_name}/rows",
    response_model=CursorPage[DataTableRow],
)
async def list_data_table_rows(
    file_id: str,
    table_name: str,
    di: Di,
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
        di=di,
    )


@router.get("/data-tables/{file_id}/tables/{table_name}/export", response_model=FileRecord)
async def export_data_table_table(
    file_id: str,
    table_name: str,
    di: Di,
    source_format: Annotated[Literal["csv", "xlsx"], Query()],
) -> FileRecord:
    return await op_data_tables_export(
        OfficeDataTableExportPayload(
            file_id=file_id, table_name=table_name, source_format=source_format
        ),
        user=require_context().user,
        di=di,
    )


@router.post(
    "/data-tables/{file_id}/tables/{table_name}/rows",
    response_model=DataTableInsertRowsResponse,
)
async def insert_data_table_rows(
    file_id: str,
    table_name: str,
    body: DataTableInsertRowsRequest,
    di: Di,
) -> DataTableInsertRowsResponse:
    return await op_data_tables_rows_insert(
        OfficeDataTableInsertRowsPayload(file_id=file_id, table_name=table_name, rows=body.rows),
        user=require_context().user,
        di=di,
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
    di: Di,
) -> DataTableUpdateRowResponse:
    return await op_data_tables_row_update(
        OfficeDataTableUpdateRowPayload(
            file_id=file_id, table_name=table_name, row_id=row_id, values=body.values
        ),
        user=require_context().user,
        di=di,
    )


@router.post(
    "/data-tables/{file_id}/tables/{table_name}/rows/delete",
    response_model=DataTableDeleteRowsResponse,
)
async def delete_data_table_rows(
    file_id: str,
    table_name: str,
    body: DataTableDeleteRowsRequest,
    di: Di,
) -> DataTableDeleteRowsResponse:
    return await op_data_tables_rows_delete(
        OfficeDataTableDeleteRowsPayload(
            file_id=file_id, table_name=table_name, row_ids=body.row_ids
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/data-tables/{file_id}/query", response_model=DataTableQueryResult)
async def query_data_table(
    file_id: str,
    body: DataTableQueryRequest,
    di: Di,
) -> DataTableQueryResult:
    return await op_data_tables_query(
        OfficeDataTableQueryPayload(file_id=file_id, sql=body.sql),
        user=require_context().user,
        di=di,
    )


@router.post(
    "/data-tables/{file_id}/import",
    response_model=DataTableSchemaSnapshot,
)
async def import_data_table_tabular(
    file_id: str,
    body: DataTableImportRequest,
    di: Di,
) -> DataTableSchemaSnapshot:
    return await op_data_tables_import(
        OfficeDataTableImportPayload(
            file_id=file_id,
            table_name=body.table_name,
            source_format=body.source_format,
            upload_file_id=body.upload_file_id,
        ),
        user=require_context().user,
        di=di,
    )
