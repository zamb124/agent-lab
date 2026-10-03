"""HTTP client for DataTable office API on top of ServiceClient."""

from __future__ import annotations

from urllib.parse import quote

from core.clients.service_client import NAMESPACE_HEADER, ServiceClient
from core.context import resolve_namespace_or_raise
from core.data_tables.models import (
    DataTableAddColumnRequest,
    DataTableCreateRequest,
    DataTableCreateTableRequest,
    DataTableDeleteRowsResponse,
    DataTableFileSnapshot,
    DataTableInsertRowsResponse,
    DataTableQueryResult,
    DataTableRow,
    DataTableSchemaSnapshot,
    DataTableScope,
    DataTableUpdateRowResponse,
)
from core.files.models import FileRecord
from core.pagination import CursorPage
from core.types import JsonObject, JsonValue, require_json_object

_API = "/documents/api/v1"


class DataTableClient:
    """REST client for office DataTable routes; namespace from context."""

    def __init__(self, service_client: ServiceClient | None = None) -> None:
        self._http: ServiceClient = (
            service_client if service_client is not None else ServiceClient()
        )

    def _ns_headers(self) -> dict[str, str]:
        return {NAMESPACE_HEADER: resolve_namespace_or_raise()}

    def _object(self, value: JsonValue, label: str) -> JsonObject:
        return require_json_object(value, label)

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
        request = DataTableCreateRequest(
            original_name=original_name,
            scope=scope,
            flow_id=flow_id,
            session_id=session_id,
            namespace=namespace,
            tables=tables if tables is not None else [],
        )
        raw = await self._http.post(
            "office",
            f"{_API}/data-tables",
            json=require_json_object(
                request.model_dump(mode="json"), "DataTableClient.create.body"
            ),
            headers=self._ns_headers(),
        )
        return FileRecord.model_validate(self._object(raw, "DataTableClient.create"))

    async def snapshot(self, file_id: str) -> DataTableFileSnapshot:
        raw = await self._http.get(
            "office",
            f"{_API}/data-tables/{quote(file_id, safe='')}",
            headers=self._ns_headers(),
        )
        return DataTableFileSnapshot.model_validate(
            self._object(raw, "DataTableClient.snapshot")
        )

    async def get_schema(self, file_id: str) -> DataTableSchemaSnapshot:
        snapshot = await self.snapshot(file_id)
        return snapshot.schema_snapshot

    async def create_table(
        self,
        file_id: str,
        request: DataTableCreateTableRequest,
    ) -> DataTableSchemaSnapshot:
        raw = await self._http.post(
            "office",
            f"{_API}/data-tables/{quote(file_id, safe='')}/tables",
            json=require_json_object(
                request.model_dump(mode="json"), "DataTableClient.create_table.body"
            ),
            headers=self._ns_headers(),
        )
        return DataTableSchemaSnapshot.model_validate(
            self._object(raw, "DataTableClient.create_table")
        )

    async def add_column(
        self,
        file_id: str,
        table_name: str,
        request: DataTableAddColumnRequest,
    ) -> DataTableSchemaSnapshot:
        raw = await self._http.post(
            "office",
            (
                f"{_API}/data-tables/{quote(file_id, safe='')}"
                f"/tables/{quote(table_name, safe='')}/columns"
            ),
            json=require_json_object(
                request.model_dump(mode="json"), "DataTableClient.add_column.body"
            ),
            headers=self._ns_headers(),
        )
        return DataTableSchemaSnapshot.model_validate(
            self._object(raw, "DataTableClient.add_column")
        )

    async def page_rows(
        self,
        file_id: str,
        table_name: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
        sort_column: str | None = None,
        sort_dir: str | None = None,
        filter_column: str | None = None,
        filter_value: str | None = None,
        q: str | None = None,
        column_q: list[str] | None = None,
    ) -> CursorPage[DataTableRow]:
        params: dict[str, str | int | list[str]] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        if sort_column is not None:
            params["sort_column"] = sort_column
        if sort_dir is not None:
            params["sort_dir"] = sort_dir
        if filter_column is not None:
            params["filter_column"] = filter_column
        if filter_value is not None:
            params["filter_value"] = filter_value
        if q is not None:
            params["q"] = q
        if column_q is not None:
            params["column_q"] = column_q
        raw = await self._http.get(
            "office",
            (
                f"{_API}/data-tables/{quote(file_id, safe='')}"
                f"/tables/{quote(table_name, safe='')}/rows"
            ),
            headers=self._ns_headers(),
            params=params,
        )
        payload = self._object(raw, "DataTableClient.page_rows")
        return CursorPage[DataTableRow].model_validate(payload)

    async def query(self, file_id: str, sql: str) -> DataTableQueryResult:
        raw = await self._http.post(
            "office",
            f"{_API}/data-tables/{quote(file_id, safe='')}/query",
            json={"sql": sql},
            headers=self._ns_headers(),
        )
        return DataTableQueryResult.model_validate(
            self._object(raw, "DataTableClient.query")
        )

    async def insert_rows(
        self,
        file_id: str,
        table_name: str,
        rows: list[JsonObject],
    ) -> list[int]:
        raw = await self._http.post(
            "office",
            (
                f"{_API}/data-tables/{quote(file_id, safe='')}"
                f"/tables/{quote(table_name, safe='')}/rows"
            ),
            json={"rows": rows},
            headers=self._ns_headers(),
        )
        payload = DataTableInsertRowsResponse.model_validate(
            self._object(raw, "DataTableClient.insert_rows")
        )
        return payload.row_ids

    async def update_row(
        self,
        file_id: str,
        table_name: str,
        row_id: int,
        values: JsonObject,
    ) -> None:
        raw = await self._http.patch(
            "office",
            (
                f"{_API}/data-tables/{quote(file_id, safe='')}"
                f"/tables/{quote(table_name, safe='')}/rows/{row_id}"
            ),
            json={"values": values},
            headers=self._ns_headers(),
        )
        _ = DataTableUpdateRowResponse.model_validate(
            self._object(raw, "DataTableClient.update_row")
        )

    async def delete_rows(
        self,
        file_id: str,
        table_name: str,
        row_ids: list[int],
    ) -> int:
        raw = await self._http.post(
            "office",
            (
                f"{_API}/data-tables/{quote(file_id, safe='')}"
                f"/tables/{quote(table_name, safe='')}/rows/delete"
            ),
            json={"row_ids": row_ids},
            headers=self._ns_headers(),
        )
        payload = DataTableDeleteRowsResponse.model_validate(
            self._object(raw, "DataTableClient.delete_rows")
        )
        return payload.deleted
