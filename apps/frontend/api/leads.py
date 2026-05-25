"""
Заявки с лендинга: запись в shared storage (ключи company:system:request:*).
"""
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.frontend.dependencies import ContainerDep, require_frontend_active_company
from apps.frontend.models import LeadCreateBody, LeadCreateResponse, LeadRequestRecord
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.logging import get_logger
from core.pagination import CursorPage, decode_cursor, encode_cursor

logger = get_logger(__name__)
REQUEST_STORAGE_PREFIX = f"company:{SYSTEM_COMPANY_ID}:request:"
LEAD_REQUEST_SCAN_LIMIT = 10_000
LEAD_REQUEST_PAGE_MAX_LIMIT = 200

leads_router = APIRouter(prefix="/api/leads", tags=["leads"])
lead_requests_router = APIRouter(prefix="/api/lead-requests", tags=["lead-requests"])


def _new_lead_request_id() -> str:
    return str(uuid.uuid4())


def _lead_request_storage_key(lead_request_id: str) -> str:
    return f"{REQUEST_STORAGE_PREFIX}{lead_request_id}"


def _lead_request_sort_key(record: LeadRequestRecord) -> tuple[datetime, str]:
    return record.created_at, record.lead_request_id


def _apply_cursor(records: list[LeadRequestRecord], cursor: str | None) -> list[LeadRequestRecord]:
    if cursor is None:
        return records
    try:
        cursor_created_at, cursor_lead_request_id = decode_cursor(cursor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [
        record
        for record in records
        if _lead_request_sort_key(record) < (cursor_created_at, cursor_lead_request_id)
    ]


def _next_cursor(items: list[LeadRequestRecord], has_more: bool) -> str | None:
    if not has_more:
        return None
    last = items[-1]
    return encode_cursor(last.created_at, last.lead_request_id)


@leads_router.post("", response_model=LeadCreateResponse)
async def create_lead(body: LeadCreateBody, container: ContainerDep) -> LeadCreateResponse:
    lead_request_id = _new_lead_request_id()
    key = _lead_request_storage_key(lead_request_id)
    record = LeadRequestRecord(
        lead_request_id=lead_request_id,
        contact_name=body.contact_name,
        email=body.email,
        phone=body.phone,
        organization_name=body.organization_name,
        comment=body.comment,
        job_title=body.job_title,
        headcount_range=body.headcount_range,
        interested_products=body.interested_products,
        created_at=datetime.now(timezone.utc),
    )
    storage = container.shared_storage
    _ = await storage.set(key, record.model_dump_json(), force_global=True)
    logger.info("Landing lead saved: %s", key)
    return LeadCreateResponse(
        message="Заявка принята. Мы свяжемся с вами в ближайшее время.",
        lead_request_id=lead_request_id,
    )


@lead_requests_router.get("", response_model=CursorPage[LeadRequestRecord])
async def list_lead_requests(
    container: ContainerDep,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=LEAD_REQUEST_PAGE_MAX_LIMIT)] = 50,
) -> CursorPage[LeadRequestRecord]:
    company = require_frontend_active_company()
    if company.company_id != SYSTEM_COMPANY_ID:
        raise HTTPException(status_code=403, detail="Доступно только для компании system")
    storage = container.shared_storage
    raw = await storage.get_all_by_prefix(
        REQUEST_STORAGE_PREFIX,
        limit=LEAD_REQUEST_SCAN_LIMIT,
        force_global=True,
    )
    records = [LeadRequestRecord.model_validate_json(value) for value in raw.values()]
    records.sort(key=_lead_request_sort_key, reverse=True)
    paged_records = _apply_cursor(records, cursor)
    window = paged_records[: limit + 1]
    has_more = len(window) > limit
    items = window[:limit]
    return CursorPage[LeadRequestRecord](
        items=items,
        next_cursor=_next_cursor(items, has_more),
        has_more=has_more,
    )
