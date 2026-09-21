"""Viz (.viz) viewer handler — native Lit ECharts/Mermaid hosts."""

from __future__ import annotations

from typing import ClassVar, cast

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
from core.files.s3_client import S3ClientFactory
from core.logging import get_logger
from core.types import JsonObject, require_json_object
from core.viz.models import VIZ_CONTENT_TYPE, parse_viz_document_bytes

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
        if not isinstance(kind_raw, str) or kind_raw not in {
            "chart",
            "flowchart",
            "gantt",
            "sequence",
            "timeline",
        }:
            raise ValueError("viz.document.kind invalid")
        if not isinstance(engine_raw, str) or engine_raw not in {"echarts", "mermaid"}:
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
                kind=cast(VizViewerKind, kind_raw),
                engine=cast(VizViewerEngine, engine_raw),
                title=title_value,
                document=document,
            ),
        )

    async def _load_document(self, file_record: FileRecord) -> JsonObject:
        s3 = S3ClientFactory.create_client_for_bucket(file_record.s3_bucket)
        try:
            body = await s3.download_bytes(file_record.s3_key)
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            logger.warning(
                "office.viz.handler.s3.error.file_id",
                file_id=file_record.file_id,
                bucket=file_record.s3_bucket,
                key=file_record.s3_key,
                code=code,
            )
            raise ValueError(f"failed to read viz file: {code}") from exc
        finally:
            await s3.close()
        viz_document = parse_viz_document_bytes(body)
        return require_json_object(viz_document.model_dump(mode="json"), "viz.document")
