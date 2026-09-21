"""Команда списка заявок с лендинга (только компания system).

Сама форма заявки — анонимный `POST /frontend/api/leads` (`apps/frontend/api/leads.py`), не команда.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from apps.frontend.container import FrontendContainer
from apps.frontend.models import LeadRequestRecord
from core.models import StrictBaseModel
from core.models.identity_models import SYSTEM_COMPANY_ID, User
from core.pagination import CursorPage, decode_cursor, encode_cursor
from core.request_scope import require_system_admin
from core.websocket import raise_invalid

REQUEST_STORAGE_PREFIX = f"company:{SYSTEM_COMPANY_ID}:request:"
LEAD_REQUEST_SCAN_LIMIT = 10_000
LEAD_REQUEST_PAGE_MAX_LIMIT = 200


class LeadRequestsListPayload(StrictBaseModel):
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=LEAD_REQUEST_PAGE_MAX_LIMIT)


def _lead_request_sort_key(record: LeadRequestRecord) -> tuple[datetime, str]:
    return record.created_at, record.lead_request_id


def _apply_cursor(records: list[LeadRequestRecord], cursor: str | None) -> list[LeadRequestRecord]:
    if cursor is None:
        return records
    try:
        cursor_created_at, cursor_lead_request_id = decode_cursor(cursor)
    except ValueError as exc:
        raise_invalid(exc)
    return [
        record for record in records if _lead_request_sort_key(record) < (cursor_created_at, cursor_lead_request_id)
    ]


async def op_lead_requests_list(
    payload: LeadRequestsListPayload, *, user: User, container: FrontendContainer
) -> CursorPage[LeadRequestRecord]:
    _ = user
    _ = await require_system_admin(container.authz_service)
    raw_records = await container.shared_storage.get_all_by_prefix(
        REQUEST_STORAGE_PREFIX, limit=LEAD_REQUEST_SCAN_LIMIT, force_global=True
    )
    records = [LeadRequestRecord.model_validate_json(value) for value in raw_records.values()]
    records.sort(key=_lead_request_sort_key, reverse=True)
    window = _apply_cursor(records, payload.cursor)[: payload.limit + 1]
    has_more = len(window) > payload.limit
    items = window[: payload.limit]
    next_cursor = encode_cursor(items[-1].created_at, items[-1].lead_request_id) if has_more else None
    return CursorPage[LeadRequestRecord](items=items, next_cursor=next_cursor, has_more=has_more)
