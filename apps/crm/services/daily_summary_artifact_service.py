"""JSON-снимки сводок CRM как FileRecord (PLATFORM_AUXILIARY)."""

from __future__ import annotations

import json

from core.context import require_active_company
from core.files.create_spec import FileCreateSpec
from core.files.models import FileRecord
from core.files.object_store.gate import FileGate
from core.files.object_store.principals import SystemPrincipal
from core.files.service import FilesService
from core.logging import get_logger
from core.types import JsonObject, parse_json_object

logger = get_logger(__name__)


def _artifact_name(kind: str, namespace: str | None, *parts: str) -> str:
    ns = "all" if namespace is None or namespace.strip() == "" else namespace.strip()
    tail = "_".join(parts)
    return f"crm-{kind}-{ns}-{tail}.json"


class DailySummaryArtifactService:
    def __init__(self) -> None:
        self._files: FilesService = FilesService(files_route_segment="crm")

    async def put_daily_payload(
        self,
        *,
        company_id: str,
        namespace: str | None,
        date_str: str,
        payload: JsonObject,
    ) -> None:
        name = _artifact_name("daily", namespace, date_str)
        await self._replace(company_id, name, payload)

    async def get_daily_payload(
        self,
        *,
        company_id: str,
        namespace: str | None,
        date_str: str,
    ) -> JsonObject | None:
        name = _artifact_name("daily", namespace, date_str)
        return await self._read(company_id, name, "daily_summary.file_payload")

    async def put_period_payload(
        self,
        *,
        company_id: str,
        namespace: str | None,
        date_from: str,
        date_to: str,
        payload: JsonObject,
    ) -> None:
        name = _artifact_name("period", namespace, date_from, date_to)
        await self._replace(company_id, name, payload)

    async def get_period_payload(
        self,
        *,
        company_id: str,
        namespace: str | None,
        date_from: str,
        date_to: str,
    ) -> JsonObject | None:
        name = _artifact_name("period", namespace, date_from, date_to)
        return await self._read(company_id, name, "period_summary.file_payload")

    async def _replace(self, company_id: str, original_name: str, payload: JsonObject) -> None:
        self._require_same_company(company_id)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        spec = FileCreateSpec.model_validate(
            {
                "source_kind": "platform_auxiliary",
                "source_ref": {},
                "retention": {"kind": "platform_default"},
                "metadata": {"artifact_name": original_name},
            }
        )
        created = await self._files.create(
            spec,
            body,
            original_name=original_name,
            content_type="application/json",
        )
        previous = await self._rows(company_id, original_name)
        for row in previous:
            if row.file_id == created.file_id:
                continue
            _ = await self._files.delete(row.file_id)
        logger.info(
            "crm.summary.artifact.stored",
            file_id=created.file_id,
            original_name=original_name,
        )

    async def _read(self, company_id: str, original_name: str, label: str) -> JsonObject | None:
        rows = await self._rows(company_id, original_name)
        if not rows:
            return None
        handle = await FileGate().open_record(rows[0], SystemPrincipal(company_id))
        raw = await handle.read_bytes()
        return parse_json_object(raw, label)

    async def _rows(self, company_id: str, original_name: str) -> list[FileRecord]:
        return await (
            FileRecord.objects.filter(
                company_id=company_id,
                original_name=original_name,
                deleted_at__isnull=True,
            )
            .order_by("-created_at")
            .limit(20)
            .all()
        )

    def _require_same_company(self, company_id: str) -> None:
        active = require_active_company().company_id
        if active != company_id:
            raise ValueError("summary artifact company_id does not match the active company")
