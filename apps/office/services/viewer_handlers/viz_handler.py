"""Viz (.viz) viewer handler — native Lit ECharts/Mermaid hosts."""

from __future__ import annotations

from typing import ClassVar

from botocore.exceptions import ClientError

from apps.office.services.viewer_context import ViewerOpenContext
from apps.office.services.viewer_handlers._urls import download_url_for_context, viewer_stream_url
from core.documents.viewer.models import (
    DocumentOpenCapabilities,
    DocumentOpenConfigResponse,
    DocumentViewerHandlerId,
    VizOpenPayload,
    VizViewerEngine,
    VizViewerKind,
)
from core.files.models import FileRecord
from core.files.object_store.gate import FileGate
from core.files.object_store.principals import SystemPrincipal
from core.logging import get_logger
from core.types import JsonObject, require_json_object
from core.viz.models import VIZ_CONTENT_TYPE, parse_viz_document_bytes

_VIZ_KINDS: tuple[VizViewerKind, ...] = ("chart", "flowchart", "gantt", "sequence", "timeline")
_VIZ_ENGINES: tuple[VizViewerEngine, ...] = ("echarts", "mermaid")


def _viz_kind(value: str) -> VizViewerKind | None:
    for kind in _VIZ_KINDS:
        if kind == value:
            return kind
    return None


def _viz_engine(value: str) -> VizViewerEngine | None:
    for engine in _VIZ_ENGINES:
        if engine == value:
            return engine
    return None

logger = get_logger(__name__)


class VizViewerHandler:
    handler_id: ClassVar[DocumentViewerHandlerId] = "viz"

    def capabilities(self, *, file_record: FileRecord, integration_configured: bool) -> DocumentOpenCapabilities:
        _ = file_record
        _ = integration_configured
        return DocumentOpenCapabilities(
            view=True,
            edit=False,
            preview=True,
            sync_on_close=False,
            download=True,
            server_mutations=False,
        )

    async def build_open_config(self, ctx: ViewerOpenContext) -> DocumentOpenConfigResponse:
        content_type = ctx.file_record.content_type or VIZ_CONTENT_TYPE
        normalized = content_type.split(";", 1)[0].strip()
        stream_url = viewer_stream_url(
            base_url=ctx.browser_public_base_url,
            handler="viz",
            viewer_scope=ctx.viewer_scope,
            file_id=ctx.file_record.file_id,
            company_id=ctx.company_id,
            content_type=normalized,
            secret=ctx.jwt_secret,
            ttl_seconds=ctx.download_token_ttl_seconds,
            public_link_token_hash=ctx.public_link_token_hash,
        )
        document = await self._load_document(ctx.file_record)
        kind_raw = document.get("kind")
        engine_raw = document.get("engine")
        title_value = document.get("title")
        kind = _viz_kind(kind_raw) if isinstance(kind_raw, str) else None
        if kind is None:
            raise ValueError("viz.document.kind invalid")
        engine = _viz_engine(engine_raw) if isinstance(engine_raw, str) else None
        if engine is None:
            raise ValueError("viz.document.engine invalid")
        if not isinstance(title_value, str) or title_value.strip() == "":
            raise ValueError("viz.document.title must be a non-empty string")
        caps = self.capabilities(file_record=ctx.file_record, integration_configured=True)
        return DocumentOpenConfigResponse(
            handler="viz",
            file_id=ctx.file_record.file_id,
            title=ctx.title,
            original_name=ctx.file_record.original_name,
            content_type=normalized,
            file_category=ctx.file_category,
            download_url=download_url_for_context(ctx) if caps.download else None,
            capabilities=caps,
            viz=VizOpenPayload(
                stream_url=stream_url,
                content_type=normalized,
                kind=kind,
                engine=engine,
                title=title_value,
                document=document,
            ),
        )

    async def _load_document(self, file_record: FileRecord) -> JsonObject:
        if file_record.company_id is None or file_record.company_id == "":
            raise ValueError("viz file has no company_id")
        try:
            handle = await FileGate().open_record(
                file_record,
                SystemPrincipal(company_id=file_record.company_id),
            )
            body = await handle.read_bytes()
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            logger.warning(
                "office.viz.handler.s3.error.file_id",
                file_id=file_record.file_id,
                storage_id=file_record.storage_id,
                key=file_record.s3_key,
                code=code,
            )
            raise ValueError(f"failed to read viz file: {code}") from exc
        viz_document = parse_viz_document_bytes(body)
        return require_json_object(viz_document.model_dump(mode="json"), "viz.document")
