"""TaskIQ: форматирование description заметки через provider_litserve /v1/text/format_markdown."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID
from apps.crm.container import get_crm_container
from apps.crm.services.crm_note_ws_broadcast import broadcast_crm_note_event
from apps.crm_worker.broker import broker
from apps.crm_worker.tasks.daily_summary_tasks import _set_crm_context
from core.clients.service_client import ServiceClient, ServiceClientError
from core.config import get_settings
from core.logging import get_logger
from core.rag.openai_http_contracts import PROVIDER_LITSERVE_PLACEHOLDER_BEARER
from core.text_transforms.format_markdown_response import validate_format_markdown_response
from core.text_transforms.strip_outer_markdown_fence import strip_outer_markdown_code_fence

logger = get_logger(__name__)


def _normalize_utc_dt(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_expected_updated_at(raw: str) -> datetime:
    s = raw.strip()
    normalized = s.replace("Z", "+00:00") if s.endswith("Z") and "+00:00" not in s else s
    parsed = datetime.fromisoformat(normalized)
    return _normalize_utc_dt(parsed)


@broker.task
async def format_note_description_markdown_task(
    note_id: str,
    company_id: str,
    namespace: str,
    auth_token: str,
    user_id: str,
    interface_language: str,
    expected_updated_at_iso: str,
) -> dict[str, Any]:
    """
    Один HTTP POST на весь текст: разбиение на чанки и батчевый ``generate`` выполняет LitServe
    ([``MarkdownFormatEngine``](apps/provider_litserve/markdown_format/engines.py)); повторять это
    циклом CRM-воркером нельзя — время растёт как число чанков подряд без общего батча на GPU.
    """
    await _set_crm_context(company_id, namespace, auth_token, user_id, interface_language=interface_language)
    container = get_crm_container()
    entity = await container.entity_repository.get(note_id)
    if entity is None:
        raise ValueError(f"Заметка не найдена: {note_id}")
    if entity.entity_type != NOTE_ROOT_ENTITY_TYPE_ID:
        return {"status": "skipped_not_note", "note_id": note_id}

    expected = _parse_expected_updated_at(expected_updated_at_iso)
    current = _normalize_utc_dt(entity.updated_at)
    delta_seconds = abs((current - expected).total_seconds())
    if delta_seconds > 0.05:
        logger.info(
            "note_markdown_format_skip_stale_updated_at",
            note_id=note_id,
            expected=expected.isoformat(),
            current=current.isoformat(),
            delta_seconds=delta_seconds,
        )
        return {"status": "skipped_stale", "note_id": note_id}

    if entity.company_id != company_id:
        raise ValueError(
            f"note_markdown_format company mismatch: entity={entity.company_id} task={company_id}"
        )

    desc = entity.description
    if desc is None or not str(desc).strip():
        return {"status": "skipped_empty_description", "note_id": note_id}

    settings = get_settings()
    infra = settings.provider_litserve.infra
    timeout = float(settings.note_markdown_format_service_timeout_seconds)
    model_id = str(infra.markdown_default_api_model_id).strip()
    if not model_id:
        raise ValueError("note_markdown_format: markdown_default_api_model_id пуст")
    chunk_lim = int(infra.markdown_max_chunk_chars)

    client = ServiceClient()
    try:
        raw = await client.post(
            "provider_litserve",
            "/v1/text/format_markdown",
            json={"text": str(desc).strip(), "model": model_id, "max_chunk_chars": chunk_lim},
            timeout=timeout,
            headers={"Authorization": f"Bearer {PROVIDER_LITSERVE_PLACEHOLDER_BEARER}"},
        )
    except ServiceClientError as exc:
        logger.warning(
            "note_markdown_format_litserve_http_failed",
            note_id=note_id,
            error=str(exc),
        )
        raise

    if not isinstance(raw, dict):
        raise ValueError("provider_litserve format_markdown: ответ не JSON-object")
    validated = validate_format_markdown_response(raw)
    markdown = strip_outer_markdown_code_fence(validated.markdown.strip())
    if not markdown:
        raise ValueError("provider_litserve format_markdown: пустой markdown")

    chunks_total = int(validated.chunks_total)
    chunks_processed = int(validated.chunks_processed)

    entity.description = markdown
    entity.updated_at = datetime.now(timezone.utc)
    merged = await container.entity_repository.update(entity)

    note_date_iso = merged.note_date.isoformat() if merged.note_date is not None else None
    await broadcast_crm_note_event(
        company_id=merged.company_id,
        namespace=merged.namespace,
        note_id=merged.entity_id,
        note_date_iso=note_date_iso,
        action="updated",
        company_repository=container.company_repository,
        access_grant_repository=container.access_grant_repository,
        skip_notification_center=False,
        markdown_format={
            "phase": "complete",
            "chunks_done": chunks_processed,
            "chunks_total": chunks_total,
        },
    )

    return {
        "status": "completed",
        "note_id": note_id,
        "chunks_total": chunks_total,
        "chunks_processed": chunks_processed,
    }
