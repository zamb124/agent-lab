"""DataTableService: SQLite FileRecord в S3, Redis lock, page/mutate."""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, assert_never, final

from botocore.exceptions import ClientError

from core.clients.redis_client import RedisClient
from core.data_tables.export_tabular import dump_tabular_bytes
from core.data_tables.identifiers import validate_ident
from core.data_tables.import_tabular import import_rows_into_new_table, parse_tabular_bytes
from core.data_tables.lock import data_table_mutation_lock
from core.data_tables.models import (
    DATA_TABLE_CONTENT_TYPE,
    DATA_TABLE_EXTENSION,
    DataTableAddColumnRequest,
    DataTableColumnSpec,
    DataTableCreateTableRequest,
    DataTableFileSnapshot,
    DataTableQueryResult,
    DataTableRow,
    DataTableSchemaSnapshot,
    DataTableScope,
    normalize_data_table_filename,
)
from core.data_tables.sql_guard import validate_user_sql
from core.data_tables.sqlite_format import (
    add_user_column,
    create_user_table,
    delete_rows,
    execute_user_sql,
    initialize_platform_schema,
    insert_rows,
    list_table_rows,
    open_sqlite,
    page_rows,
    read_schema_snapshot,
    update_row,
)
from core.documents.placement import DocumentPlacement
from core.files.checksum import compute_content_checksum_sha256
from core.files.create_spec import FileCreateSpec, FilePostCreate, FileSourceKind, FileSourceRef
from core.files.models import FileRecord
from core.files.object_store.gate import FileGate
from core.files.object_store.principals import SystemPrincipal
from core.files.registry import default_retention_for_source
from core.files.service import FilesService
from core.files.types import FileCategory, ext_to_category
from core.logging import get_logger
from core.pagination import CursorPage
from core.types import JsonObject, JsonValue, require_json_object

logger = get_logger(__name__)

SqliteWriter = Callable[[sqlite3.Connection], None]


class DataTableNotFoundError(ValueError):
    """FileRecord не найден или не DATA_TABLE."""


def _source_kind_for_scope(scope: DataTableScope) -> FileSourceKind:
    if scope == "flow_asset":
        return FileSourceKind.FLOW_ASSET
    if scope == "flow_session":
        return FileSourceKind.FLOW_SESSION
    if scope == "office_document":
        return FileSourceKind.OFFICE_DOCUMENT
    assert_never(scope)


@final
class DataTableService:
    _files_service: FilesService
    _redis_client: RedisClient

    def __init__(
        self,
        *,
        files_service: FilesService,
        redis_client: RedisClient,
    ) -> None:
        self._files_service = files_service
        self._redis_client = redis_client

    async def create(
        self,
        *,
        original_name: str,
        scope: DataTableScope,
        flow_id: str | None = None,
        session_id: str | None = None,
        tables: list[DataTableCreateTableRequest] | None = None,
        namespace: str | None = None,
    ) -> FileRecord:
        filename = normalize_data_table_filename(original_name)
        source_kind = _source_kind_for_scope(scope)
        if source_kind == FileSourceKind.FLOW_ASSET and (flow_id is None or not flow_id.strip()):
            raise ValueError("flow_id is required for flow_asset DataTable")
        if source_kind == FileSourceKind.FLOW_SESSION:
            if flow_id is None or not flow_id.strip():
                raise ValueError("flow_id is required for flow_session DataTable")
            if session_id is None or not session_id.strip():
                raise ValueError("session_id is required for flow_session DataTable")
        if source_kind == FileSourceKind.OFFICE_DOCUMENT and (
            namespace is None or not namespace.strip()
        ):
            raise ValueError("namespace is required for office_document DataTable")
        metadata: dict[str, JsonValue] = {}
        if flow_id is not None:
            metadata["flow_id"] = flow_id
        if session_id is not None:
            metadata["session_id"] = session_id
        office_placement = (
            DocumentPlacement(catalog_path=["Tables"])
            if source_kind is FileSourceKind.OFFICE_DOCUMENT
            else None
        )
        spec = FileCreateSpec(
            source_kind=source_kind,
            source_ref=FileSourceRef(
                flow_id=flow_id,
                session_id=session_id,
            ),
            retention=default_retention_for_source(source_kind),
            placement=office_placement,
            post_create=FilePostCreate(is_public=False),
            metadata=require_json_object(metadata, "data_table.create.metadata")
            if metadata
            else None,
        )
        payload = self._build_empty_bytes(
            scope=scope,
            flow_id=flow_id,
            session_id=session_id,
            tables=tables if tables is not None else [],
        )
        return await self._files_service.create(
            spec,
            payload,
            original_name=filename,
            content_type=DATA_TABLE_CONTENT_TYPE,
            content_sha256_hex=compute_content_checksum_sha256(payload),
        )

    async def promote_session_to_asset(
        self,
        file_id: str,
        *,
        flow_id: str,
        original_name: str | None = None,
    ) -> FileRecord:
        record = await self._require_record(file_id)
        snapshot = await self.get_schema(file_id)
        if snapshot.scope != "flow_session":
            raise ValueError("promote requires scope=flow_session")
        body = await self._download_bytes(record)
        filename = original_name if original_name is not None else record.original_name
        name = normalize_data_table_filename(filename)
        spec = FileCreateSpec(
            source_kind=FileSourceKind.FLOW_ASSET,
            source_ref=FileSourceRef(flow_id=flow_id),
            retention=default_retention_for_source(FileSourceKind.FLOW_ASSET),
            post_create=FilePostCreate(is_public=False),
            metadata=require_json_object({"flow_id": flow_id}, "data_table.promote.metadata"),
        )
        return await self._files_service.create(
            spec,
            body,
            original_name=name,
            content_type=DATA_TABLE_CONTENT_TYPE,
            content_sha256_hex=compute_content_checksum_sha256(body),
        )

    async def get_schema(self, file_id: str) -> DataTableSchemaSnapshot:
        record = await self._require_record(file_id)
        async with self._sqlite_file(record) as prepared:
            connection, path, original = prepared
            snapshot = read_schema_snapshot(connection)
            mutated = path.read_bytes()
        if hashlib.sha256(original).digest() != hashlib.sha256(mutated).digest():
            async with data_table_mutation_lock(self._redis_client, file_id):
                fresh = await self._require_record(file_id)
                current = await self._download_bytes(fresh)
                if hashlib.sha256(current).digest() == hashlib.sha256(original).digest():
                    _ = await self._upload_replaced(fresh, mutated)
                    return snapshot
            return await self.get_schema(file_id)
        return snapshot

    async def snapshot(self, file_id: str) -> DataTableFileSnapshot:
        record = await self._require_record(file_id)
        schema_snapshot = await self.get_schema(file_id)
        return DataTableFileSnapshot(
            file_id=record.file_id,
            original_name=record.original_name,
            content_type=record.content_type,
            file_size=record.file_size,
            checksum=record.checksum,
            schema_snapshot=schema_snapshot,
        )

    async def list_tables(self, file_id: str) -> DataTableSchemaSnapshot:
        return await self.get_schema(file_id)

    async def create_table(
        self, file_id: str, request: DataTableCreateTableRequest
    ) -> DataTableSchemaSnapshot:
        async with data_table_mutation_lock(self._redis_client, file_id):
            record = await self._require_record(file_id)

            def _write(connection: sqlite3.Connection) -> None:
                create_user_table(
                    connection,
                    table_name=request.name,
                    columns=request.columns,
                )

            return await self._mutate(record, _write)

    async def add_column(
        self,
        file_id: str,
        table_name: str,
        request: DataTableAddColumnRequest,
    ) -> DataTableSchemaSnapshot:
        async with data_table_mutation_lock(self._redis_client, file_id):
            record = await self._require_record(file_id)
            spec = DataTableColumnSpec(
                name=request.name,
                column_type=request.column_type,
                not_null=request.not_null,
            )

            def _write(connection: sqlite3.Connection) -> None:
                add_user_column(connection, table_name=table_name, spec=spec)

            return await self._mutate(record, _write)

    async def insert_rows(
        self,
        file_id: str,
        table_name: str,
        rows: list[JsonObject],
    ) -> list[int]:
        inserted: list[int] = []
        async with data_table_mutation_lock(self._redis_client, file_id):
            record = await self._require_record(file_id)

            def _write(connection: sqlite3.Connection) -> None:
                inserted.extend(insert_rows(connection, table_name=table_name, rows=rows))

            _ = await self._mutate(record, _write)
        return inserted

    async def update_row(
        self,
        file_id: str,
        table_name: str,
        row_id: int,
        values: JsonObject,
    ) -> None:
        async with data_table_mutation_lock(self._redis_client, file_id):
            record = await self._require_record(file_id)

            def _write(connection: sqlite3.Connection) -> None:
                update_row(
                    connection,
                    table_name=table_name,
                    row_id=row_id,
                    values=values,
                )

            _ = await self._mutate(record, _write)

    async def delete_rows(self, file_id: str, table_name: str, row_ids: list[int]) -> int:
        deleted_holder: list[int] = []
        async with data_table_mutation_lock(self._redis_client, file_id):
            record = await self._require_record(file_id)

            def _write(connection: sqlite3.Connection) -> None:
                deleted_holder.append(
                    delete_rows(connection, table_name=table_name, row_ids=row_ids)
                )

            _ = await self._mutate(record, _write)
        return deleted_holder[0]

    async def page_rows(
        self,
        file_id: str,
        table_name: str,
        *,
        limit: int,
        cursor: str | None = None,
        sort_column: str | None = None,
        sort_dir: Literal["asc", "desc"] = "asc",
        filter_column: str | None = None,
        filter_value: str | None = None,
        q: str | None = None,
        column_q: list[str] | None = None,
    ) -> CursorPage[DataTableRow]:
        record = await self._require_record(file_id)
        async with self._sqlite_file(record) as prepared:
            connection, _path, _original = prepared
            return page_rows(
                connection,
                table_name=table_name,
                limit=limit,
                cursor=cursor,
                sort_column=sort_column,
                sort_dir=sort_dir,
                filter_column=filter_column,
                filter_value=filter_value,
                q=q,
                column_q=column_q,
            )

    async def query(self, file_id: str, sql: str) -> DataTableQueryResult:
        record = await self._require_record(file_id)
        stripped = sql.strip().lower()
        is_write = stripped.startswith(("insert", "update", "delete"))
        if is_write:
            result = DataTableQueryResult(columns=[], rows=[], row_count=0)
            async with data_table_mutation_lock(self._redis_client, file_id):
                record = await self._require_record(file_id)

                def _write(connection: sqlite3.Connection) -> None:
                    snapshot = read_schema_snapshot(connection)
                    allowed = frozenset(table.name for table in snapshot.tables)
                    guarded = validate_user_sql(sql, allowed_tables=allowed)
                    columns, rows = execute_user_sql(connection, guarded)
                    result.columns = columns
                    result.rows = rows
                    result.row_count = len(rows)

                _ = await self._mutate(record, _write)
            return result
        async with self._sqlite_file(record) as prepared:
            connection, _path, _original = prepared
            snapshot = read_schema_snapshot(connection)
            allowed = frozenset(table.name for table in snapshot.tables)
            guarded = validate_user_sql(sql, allowed_tables=allowed)
            columns, rows = execute_user_sql(connection, guarded)
            return DataTableQueryResult(columns=columns, rows=rows, row_count=len(rows))

    async def export_tabular(
        self,
        file_id: str,
        *,
        table_name: str,
        source_format: Literal["csv", "xlsx"],
    ) -> tuple[bytes, str]:
        ident = validate_ident(table_name, kind="table")
        record = await self._require_record(file_id)
        async with self._sqlite_file(record) as prepared:
            connection, _path, _original = prepared
            columns, rows = list_table_rows(connection, table_name=ident)
            payload = dump_tabular_bytes(
                columns,
                rows,
                table_name=ident,
                source_format=source_format,
            )
        filename = f"{ident}.{source_format}"
        return payload, filename

    async def import_tabular(
        self,
        file_id: str,
        *,
        table_name: str,
        source_format: Literal["csv", "xlsx"],
        raw: bytes,
    ) -> DataTableSchemaSnapshot:
        _ = validate_ident(table_name, kind="table")
        columns, rows = parse_tabular_bytes(raw, source_format=source_format)
        async with data_table_mutation_lock(self._redis_client, file_id):
            record = await self._require_record(file_id)

            def _write(connection: sqlite3.Connection) -> None:
                _ = import_rows_into_new_table(
                    connection,
                    table_name=table_name,
                    columns=columns,
                    rows=rows,
                )

            return await self._mutate(record, _write)

    def _build_empty_bytes(
        self,
        *,
        scope: DataTableScope,
        flow_id: str | None,
        session_id: str | None,
        tables: list[DataTableCreateTableRequest],
    ) -> bytes:
        tmp = tempfile.NamedTemporaryFile(suffix=DATA_TABLE_EXTENSION, delete=False)
        path = Path(tmp.name)
        tmp.close()
        connection = open_sqlite(path)
        try:
            initialize_platform_schema(
                connection,
                scope=scope,
                flow_id=flow_id,
                session_id=session_id,
            )
            for table in tables:
                create_user_table(
                    connection,
                    table_name=table.name,
                    columns=table.columns,
                )
        finally:
            connection.close()
        payload = path.read_bytes()
        path.unlink()
        return payload

    async def _require_record(self, file_id: str) -> FileRecord:
        record = await self._files_service.get_optional(file_id)
        if record is None:
            raise DataTableNotFoundError(f"file not found: {file_id}")
        category = ext_to_category(Path(record.original_name).suffix.lower())
        if category != FileCategory.DATA_TABLE:
            raise DataTableNotFoundError(f"file {file_id} is not a DataTable")
        return record

    def _scope_from_record(self, record: FileRecord) -> DataTableScope:
        source_kind = record.metadata.get("source_kind")
        if source_kind == FileSourceKind.FLOW_ASSET.value:
            return "flow_asset"
        if source_kind == FileSourceKind.FLOW_SESSION.value:
            return "flow_session"
        return "office_document"

    def _flow_id_from_record(self, record: FileRecord) -> str | None:
        raw = record.metadata.get("flow_id")
        if isinstance(raw, str) and raw.strip():
            return raw
        return None

    def _session_id_from_record(self, record: FileRecord) -> str | None:
        raw = record.metadata.get("session_id")
        if isinstance(raw, str) and raw.strip():
            return raw
        return None

    async def _download_bytes(self, record: FileRecord) -> bytes:
        if record.company_id is None or record.company_id == "":
            raise DataTableNotFoundError(f"DataTable {record.file_id} has no company")
        try:
            handle = await FileGate().open_record(
                record,
                SystemPrincipal(company_id=record.company_id),
            )
            return await handle.read_bytes()
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            logger.warning(
                "data_tables.data.table.s3.error.file_id",
                file_id=record.file_id,
                storage_id=record.storage_id,
                key=record.s3_key,
                code=code,
            )
            raise DataTableNotFoundError(f"failed to read DataTable: {code}") from exc

    @asynccontextmanager
    async def _sqlite_file(
        self, record: FileRecord
    ) -> AsyncGenerator[tuple[sqlite3.Connection, Path, bytes], None]:
        body = await self._download_bytes(record)
        tmp = tempfile.NamedTemporaryFile(suffix=DATA_TABLE_EXTENSION, delete=False)
        path = Path(tmp.name)
        tmp.close()
        _ = path.write_bytes(body)
        connection = open_sqlite(path)
        try:
            initialize_platform_schema(
                connection,
                scope=self._scope_from_record(record),
                flow_id=self._flow_id_from_record(record),
                session_id=self._session_id_from_record(record),
            )
            yield connection, path, body
        finally:
            connection.close()
            if path.exists():
                path.unlink()

    async def _mutate(
        self,
        record: FileRecord,
        writer: SqliteWriter,
    ) -> DataTableSchemaSnapshot:
        async with self._sqlite_file(record) as prepared:
            connection, path, _original = prepared
            writer(connection)
            snapshot = read_schema_snapshot(connection)
            payload = path.read_bytes()
        _ = await self._upload_replaced(record, payload)
        return snapshot

    async def _upload_replaced(self, record: FileRecord, data: bytes) -> FileRecord:
        if len(data) == 0:
            raise ValueError("DataTable file cannot be empty")
        suffix = Path(record.original_name).suffix.lower()
        if suffix not in {DATA_TABLE_EXTENSION, ".db", ""}:
            raise ValueError(
                f"DataTable original_name must use {DATA_TABLE_EXTENSION}, got {record.original_name!r}"
            )
        return await self._files_service.replace_content(
            record,
            data,
            content_type=DATA_TABLE_CONTENT_TYPE,
            expected_checksum=record.checksum,
        )
