"""
API платформенного календаря.
"""

from __future__ import annotations

from datetime import datetime
from typing import NoReturn
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from core.context import get_context
from core.di.platform import Di
from core.models import (
    CalendarEvent,
    CalendarEventSource,
    CalendarEventUpsertPayload,
    CalendarIntegration,
    CalendarIntegrationConnectPayload,
)
from core.pagination import ListResponse
from core.utils.domain import get_host_with_port, is_local

router = APIRouter(tags=["calendar"])


class CalendarListRequest(BaseModel):
    start_at: datetime
    end_at: datetime
    include_sources: list[CalendarEventSource] | None = None
    limit: int = Field(default=1000, ge=1, le=5000)


class CalendarUpsertRequest(CalendarEventUpsertPayload):
    pass


class CalendarConnectIntegrationRequest(CalendarIntegrationConnectPayload):
    pass


class CalendarSyncRequest(BaseModel):
    integration_id: str
    start_at: datetime
    end_at: datetime


class CalendarListResponse(BaseModel):
    events: list[CalendarEvent]
    integrations: list[CalendarIntegration]


def _raise_http_for_calendar_service_error(error: Exception) -> NoReturn:
    message = str(error)
    if isinstance(error, ValueError):
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from error
    if isinstance(error, RuntimeError):
        raise HTTPException(status_code=502, detail=message) from error
    raise error


def _append_query(url: str, params: dict[str, str]) -> str:
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(params)
    next_query = urlencode(query)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, next_query, parsed.fragment))


@router.post("/events/list", response_model=CalendarListResponse)
async def list_calendar_events(payload: CalendarListRequest, di: Di) -> CalendarListResponse:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        events = await di.calendar_service.list_events_by_start_at_asc(
            company_id=ctx.active_company.company_id,
            user_id=ctx.user.user_id,
            start_at=payload.start_at,
            end_at=payload.end_at,
            include_sources=set(payload.include_sources) if payload.include_sources else None,
            limit=payload.limit,
        )
        integrations = await di.calendar_service.list_integrations(
            user_id=ctx.user.user_id,
            company_id=ctx.active_company.company_id,
        )
    except Exception as exc:
        _raise_http_for_calendar_service_error(exc)
    return CalendarListResponse(events=events, integrations=integrations)


@router.post("/events", response_model=CalendarEvent)
async def create_calendar_event(payload: CalendarUpsertRequest, di: Di) -> CalendarEvent:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return await di.calendar_service.upsert_event(
            event_id=None,
            payload=payload,
            user_id=ctx.user.user_id,
            company_id=ctx.active_company.company_id,
        )
    except Exception as exc:
        _raise_http_for_calendar_service_error(exc)


@router.put("/events/{event_id}", response_model=CalendarEvent)
async def update_calendar_event(event_id: str, payload: CalendarUpsertRequest, di: Di) -> CalendarEvent:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return await di.calendar_service.upsert_event(
            event_id=event_id,
            payload=payload,
            user_id=ctx.user.user_id,
            company_id=ctx.active_company.company_id,
        )
    except Exception as exc:
        _raise_http_for_calendar_service_error(exc)


@router.delete("/events/{event_id}")
async def delete_calendar_event(event_id: str, di: Di) -> dict[str, bool]:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        await di.calendar_service.delete_event(
            event_id=event_id,
            company_id=ctx.active_company.company_id,
        )
    except Exception as exc:
        _raise_http_for_calendar_service_error(exc)
    return {"success": True}


@router.get("/integrations", response_model=ListResponse[CalendarIntegration])
async def list_calendar_integrations(di: Di) -> ListResponse[CalendarIntegration]:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        integrations = await di.calendar_service.list_integrations(
            user_id=ctx.user.user_id,
            company_id=ctx.active_company.company_id,
        )
        return ListResponse[CalendarIntegration](items=integrations)
    except Exception as exc:
        _raise_http_for_calendar_service_error(exc)


@router.post("/integrations/connect", response_model=CalendarIntegration)
async def connect_calendar_integration(
    payload: CalendarConnectIntegrationRequest,
    di: Di,
) -> CalendarIntegration:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        integration = await di.calendar_service.connect_integration(
            user_id=ctx.user.user_id,
            company_id=ctx.active_company.company_id,
            payload=payload,
        )
        return integration
    except Exception as exc:
        _raise_http_for_calendar_service_error(exc)


@router.get("/integrations/google/start")
async def start_google_calendar_oauth(
    request: Request,
    di: Di,
    return_path: str = "/",
) -> RedirectResponse:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not return_path.startswith("/") or return_path.startswith("//"):
        raise HTTPException(status_code=400, detail="return_path must start with single '/'")
    original_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if not original_host:
        raise HTTPException(status_code=400, detail="Host header is required")
    forwarded_proto = request.headers.get("x-forwarded-proto")
    protocol = forwarded_proto if forwarded_proto else ("http" if is_local(original_host) else "https")
    base_host = get_host_with_port(original_host)
    redirect_uri = f"{protocol}://{base_host}/auth/callback/google"
    try:
        auth_url = await di.calendar_service.start_google_oauth(
            user_id=ctx.user.user_id,
            company_id=ctx.active_company.company_id,
            redirect_uri=redirect_uri,
            return_path=return_path,
        )
    except Exception as exc:
        _raise_http_for_calendar_service_error(exc)
    return RedirectResponse(url=auth_url)


@router.get("/integrations/google/callback")
async def complete_google_calendar_oauth(
    di: Di,
    state: str,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Google OAuth code is required")
    try:
        return_path = await di.calendar_service.complete_google_oauth(
            state=state,
            code=code,
        )
    except Exception as exc:
        _raise_http_for_calendar_service_error(exc)
    redirect_url = _append_query(
        return_path,
        {
            "calendar_provider": "google",
            "calendar_status": "connected",
        },
    )
    return RedirectResponse(url=redirect_url)


@router.delete("/integrations/{integration_id}")
async def disconnect_calendar_integration(integration_id: str, di: Di) -> dict[str, bool]:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        await di.calendar_service.disconnect_integration(
            user_id=ctx.user.user_id,
            company_id=ctx.active_company.company_id,
            integration_id=integration_id,
        )
    except Exception as exc:
        _raise_http_for_calendar_service_error(exc)
    return {"success": True}


@router.post("/sync")
async def sync_calendar(payload: CalendarSyncRequest, di: Di) -> dict[str, int]:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return await di.calendar_service.run_sync(
            user_id=ctx.user.user_id,
            company_id=ctx.active_company.company_id,
            start_at=payload.start_at,
            end_at=payload.end_at,
            integration_id=payload.integration_id,
        )
    except Exception as exc:
        _raise_http_for_calendar_service_error(exc)
