"""Заявки с лендинга: анонимная форма (протокол публичного сайта) и REST-зеркало списка для system."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Query

from apps.frontend.di import Di
from apps.frontend.models import LeadCreateBody, LeadCreateResponse, LeadRequestRecord
from apps.frontend.realtime.leads_operations import (
    LEAD_REQUEST_PAGE_MAX_LIMIT,
    REQUEST_STORAGE_PREFIX,
    LeadRequestsListPayload,
    op_lead_requests_list,
)
from core.context import require_context
from core.logging import get_logger
from core.pagination import CursorPage

logger = get_logger(__name__)

leads_router = APIRouter(prefix="/api/leads", tags=["leads"])
lead_requests_router = APIRouter(prefix="/api/lead-requests", tags=["lead-requests"])


@leads_router.post("", response_model=LeadCreateResponse)
async def create_lead(body: LeadCreateBody, di: Di) -> LeadCreateResponse:
    """Публичная форма лендинга: запись в shared storage компании system без сессии."""
    lead_request_id = str(uuid.uuid4())
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
    _ = await di.shared_storage.set(
        f"{REQUEST_STORAGE_PREFIX}{lead_request_id}", record.model_dump_json()
    )
    logger.info("landing.lead_saved", lead_request_id=lead_request_id)
    return LeadCreateResponse(
        message="Заявка принята. Мы свяжемся с вами в ближайшее время.",
        lead_request_id=lead_request_id,
    )


@lead_requests_router.get("", response_model=CursorPage[LeadRequestRecord])
async def list_lead_requests(
    di: Di,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=LEAD_REQUEST_PAGE_MAX_LIMIT)] = 50,
) -> CursorPage[LeadRequestRecord]:
    return await op_lead_requests_list(
        LeadRequestsListPayload(cursor=cursor, limit=limit), user=require_context().user, di=di
    )
