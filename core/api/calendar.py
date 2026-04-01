"""
API платформенного календаря.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core.calendar.service import CalendarService
from core.context import get_context
from core.models import (
    CalendarAttendee,
    CalendarEvent,
    CalendarEventSource,
    CalendarEventStatus,
    CalendarIntegration,
    CalendarProvider,
)
from core.utils.domain import get_host_with_port, is_local

router = APIRouter(tags=["calendar"])


class CalendarListRequest(BaseModel):
    start_at: datetime
    end_at: datetime
    include_sources: list[CalendarEventSource] | None = None
    limit: int = Field(default=1000, ge=1, le=5000)


class CalendarSyncMeetingPayload(BaseModel):
    """Встреча Sync: новый канал и ссылка создаются в Sync при сохранении события (см. CalendarService)."""

    enabled: bool = False


class CalendarUpsertRequest(BaseModel):
    title: str
    kind: str = "event"
    source: CalendarEventSource = CalendarEventSource.PLATFORM
    source_id: str | None = None
    namespace: str | None = None
    description: str | None = None
    location: str | None = None
    status: CalendarEventStatus = CalendarEventStatus.CONFIRMED
    timezone: str = "UTC"
    all_day: bool = False
    start_at: datetime
    end_at: datetime
    attendees: list[CalendarAttendee] = Field(default_factory=list)
    recurrence_rule: str | None = None
    recurrence_id: str | None = None
    series_id: str | None = None
    deep_link: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    sync_meeting: CalendarSyncMeetingPayload | None = None


class CalendarConnectIntegrationRequest(BaseModel):
    provider: CalendarProvider
    username: str | None = None
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    scope: str | None = None
    token_type: str | None = None
    default_calendar_id: str | None = None
    sync_enabled: bool = True
    sync_inbound_enabled: bool = True
    sync_outbound_enabled: bool = True
    notifications_enabled: bool = True


class CalendarSyncRequest(BaseModel):
    provider: CalendarProvider
    start_at: datetime
    end_at: datetime


class CalendarIntegrationPublic(BaseModel):
    integration_id: str
    company_id: str
    user_id: str
    provider: CalendarProvider
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class CalendarListResponse(BaseModel):
    events: list[CalendarEvent]
    integrations: list[CalendarIntegrationPublic]


def _to_public_integration(integration: CalendarIntegration) -> CalendarIntegrationPublic:
    return CalendarIntegrationPublic(
        integration_id=integration.integration_id,
        company_id=integration.company_id,
        user_id=integration.user_id,
        provider=integration.provider,
        settings=integration.settings.model_dump(mode="json"),
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


def _get_calendar_service(request: Request) -> CalendarService:
    return request.app.state.container.calendar_service


CalendarServiceDep = Annotated[CalendarService, Depends(_get_calendar_service)]


def _raise_http_for_calendar_service_error(error: Exception) -> None:
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
async def list_calendar_events(payload: CalendarListRequest, service: CalendarServiceDep) -> CalendarListResponse:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        events = await service.list_events(
            company_id=ctx.active_company.company_id,
            user_id=ctx.user.user_id,
            start_at=payload.start_at,
            end_at=payload.end_at,
            include_sources=set(payload.include_sources) if payload.include_sources else None,
            limit=payload.limit,
        )
        integrations = await service.list_integrations(
            user_id=ctx.user.user_id,
            company_id=ctx.active_company.company_id,
        )
    except Exception as error:
        _raise_http_for_calendar_service_error(error)
    public_integrations = [_to_public_integration(item) for item in integrations]
    return CalendarListResponse(events=events, integrations=public_integrations)


@router.post("/events", response_model=CalendarEvent)
async def create_calendar_event(payload: CalendarUpsertRequest, service: CalendarServiceDep) -> CalendarEvent:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return await service.upsert_event(
            event_id=None,
            payload=payload.model_dump(),
            user_id=ctx.user.user_id,
            company_id=ctx.active_company.company_id,
        )
    except Exception as error:
        _raise_http_for_calendar_service_error(error)


@router.put("/events/{event_id}", response_model=CalendarEvent)
async def update_calendar_event(event_id: str, payload: CalendarUpsertRequest, service: CalendarServiceDep) -> CalendarEvent:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return await service.upsert_event(
            event_id=event_id,
            payload=payload.model_dump(),
            user_id=ctx.user.user_id,
            company_id=ctx.active_company.company_id,
        )
    except Exception as error:
        _raise_http_for_calendar_service_error(error)


@router.delete("/events/{event_id}")
async def delete_calendar_event(event_id: str, service: CalendarServiceDep) -> dict[str, bool]:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        await service.delete_event(
            event_id=event_id,
            user_id=ctx.user.user_id,
            company_id=ctx.active_company.company_id,
        )
    except Exception as error:
        _raise_http_for_calendar_service_error(error)
    return {"success": True}


@router.get("/integrations", response_model=list[CalendarIntegrationPublic])
async def list_calendar_integrations(service: CalendarServiceDep) -> list[CalendarIntegrationPublic]:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        integrations = await service.list_integrations(
            user_id=ctx.user.user_id,
            company_id=ctx.active_company.company_id,
        )
        return [_to_public_integration(item) for item in integrations]
    except Exception as error:
        _raise_http_for_calendar_service_error(error)


@router.post("/integrations/connect", response_model=CalendarIntegrationPublic)
async def connect_calendar_integration(
    payload: CalendarConnectIntegrationRequest,
    service: CalendarServiceDep,
) -> CalendarIntegrationPublic:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        integration = await service.connect_integration(
            user_id=ctx.user.user_id,
            company_id=ctx.active_company.company_id,
            payload=payload.model_dump(),
        )
        return _to_public_integration(integration)
    except Exception as error:
        _raise_http_for_calendar_service_error(error)


@router.get("/integrations/google/start")
async def start_google_calendar_oauth(
    request: Request,
    service: CalendarServiceDep,
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
        auth_url = await service.start_google_oauth(
            user_id=ctx.user.user_id,
            company_id=ctx.active_company.company_id,
            redirect_uri=redirect_uri,
            return_path=return_path,
        )
    except Exception as error:
        _raise_http_for_calendar_service_error(error)
    return RedirectResponse(url=auth_url)


@router.get("/integrations/google/callback")
async def complete_google_calendar_oauth(
    service: CalendarServiceDep,
    state: str,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Google OAuth code is required")
    try:
        return_path = await service.complete_google_oauth(
            state=state,
            code=code,
        )
    except Exception as error:
        _raise_http_for_calendar_service_error(error)
    redirect_url = _append_query(
        return_path,
        {
            "calendar_provider": "google",
            "calendar_status": "connected",
        },
    )
    return RedirectResponse(url=redirect_url)


@router.delete("/integrations/{provider}")
async def disconnect_calendar_integration(provider: CalendarProvider, service: CalendarServiceDep) -> dict[str, bool]:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        await service.disconnect_integration(
            user_id=ctx.user.user_id,
            company_id=ctx.active_company.company_id,
            provider=provider,
        )
    except Exception as error:
        _raise_http_for_calendar_service_error(error)
    return {"success": True}


@router.post("/sync")
async def sync_calendar(payload: CalendarSyncRequest, service: CalendarServiceDep) -> dict[str, int]:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return await service.run_sync(
            user_id=ctx.user.user_id,
            company_id=ctx.active_company.company_id,
            start_at=payload.start_at,
            end_at=payload.end_at,
            provider=payload.provider,
        )
    except Exception as error:
        _raise_http_for_calendar_service_error(error)
