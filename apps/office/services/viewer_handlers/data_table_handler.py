"""DataTable (.sqlite) viewer handler — native Lit grid host."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import ClassVar

from botocore.exceptions import ClientError

from apps.office.services.viewer_context import ViewerOpenContext
from apps.office.services.viewer_handlers._urls import download_url_for_context
from core.data_tables.models import DATA_TABLE_CONTENT_TYPE
from core.data_tables.sqlite_format import (
    initialize_platform_schema,
    open_sqlite,
    read_schema_snapshot,
)
from core.documents.viewer.models import (
    DataTableOpenPayload,
    DataTableViewerScope,
    DocumentOpenCapabilities,
    DocumentOpenConfigResponse,
    DocumentViewerHandlerId,
)
from core.files.create_spec import FileSourceKind
from core.files.models import FileRecord
from core.files.object_store.gate import FileGate
from core.files.object_store.principals import SystemPrincipal
from core.logging import get_logger

logger = get_logger(__name__)


class DataTableViewerHandler:
    handler_id: ClassVar[DocumentViewerHandlerId] = "data_table"

    def capabilities(
        self, *, file_record: FileRecord, integration_configured: bool
    ) -> DocumentOpenCapabilities:
        _ = file_record
        _ = integration_configured
        return DocumentOpenCapabilities(
            view=True,
            edit=True,
            preview=True,
            sync_on_close=False,
            download=True,
            server_mutations=True,
        )

    async def build_open_config(self, ctx: ViewerOpenContext) -> DocumentOpenConfigResponse:
        content_type = ctx.file_record.content_type or DATA_TABLE_CONTENT_TYPE
        normalized = content_type.split(";", 1)[0].strip()
        schema_snapshot = await self._load_schema(ctx.file_record)
        scope = schema_snapshot.scope
        file_id = ctx.file_record.file_id
        caps = self.capabilities(file_record=ctx.file_record, integration_configured=True)
        return DocumentOpenConfigResponse(
            handler="data_table",
            file_id=file_id,
            title=ctx.title,
            original_name=ctx.file_record.original_name,
            content_type=normalized,
            file_category=ctx.file_category,
            download_url=download_url_for_context(ctx) if caps.download else None,
            capabilities=caps,
            data_table=DataTableOpenPayload(
                file_id=file_id,
                schema_snapshot=schema_snapshot,
                rows_url=f"/documents/api/v1/data-tables/{file_id}/tables",
                mutate_url=f"/documents/api/v1/data-tables/{file_id}",
                scope=scope,
                flow_id=schema_snapshot.flow_id,
                session_id=schema_snapshot.session_id,
            ),
        )

    async def _load_schema(self, file_record: FileRecord):
        if file_record.company_id is None or file_record.company_id == "":
            raise ValueError("DataTable file has no company_id")
        try:
            handle = await FileGate().open_record(
                file_record,
                SystemPrincipal(company_id=file_record.company_id),
            )
            body = await handle.read_bytes()
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            logger.warning(
                "office.data.table.handler.s3.error",
                file_id=file_record.file_id,
                storage_id=file_record.storage_id,
                key=file_record.s3_key,
                code=code,
            )
            raise ValueError(f"failed to read DataTable file: {code}") from exc
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        path = Path(tmp.name)
        _ = tmp.write(body)
        tmp.close()
        connection = open_sqlite(path)
        try:
            initialize_platform_schema(
                connection,
                scope=_scope_from_record(file_record),
                flow_id=_meta_str(file_record, "flow_id"),
                session_id=_meta_str(file_record, "session_id"),
            )
            return read_schema_snapshot(connection)
        finally:
            connection.close()
            if path.exists():
                path.unlink()


def _scope_from_record(file_record: FileRecord) -> DataTableViewerScope:
    source_kind = file_record.metadata.get("source_kind")
    if source_kind == FileSourceKind.FLOW_ASSET.value:
        return "flow_asset"
    if source_kind == FileSourceKind.FLOW_SESSION.value:
        return "flow_session"
    return "office_document"


def _meta_str(file_record: FileRecord, key: str) -> str | None:
    raw = file_record.metadata.get(key)
    if isinstance(raw, str) and raw.strip():
        return raw
    return None
