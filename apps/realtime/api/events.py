"""Снимок PlatformEvent по event_id."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from apps.realtime.di import Di
from core.context import get_context
from core.events.contract import PlatformEvent
from core.models.context_models import Context

router = APIRouter()


@router.get("/events/{event_id}/terminal", response_model=PlatformEvent)
async def get_terminal_platform_event(event_id: str, di: Di) -> PlatformEvent:
    context = get_context()
    if context is None:
        raise RuntimeError("get_terminal_platform_event requires request context")
    try:
        terminal = await di.bus_service.get_terminal_for_causation(event_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"terminal for {event_id} not found") from None
    _require_readable_snapshot(
        terminal,
        user_id=context.user.user_id,
        company_id=_require_active_company_id(context),
        not_found_detail=f"terminal for {event_id} not found",
    )
    return terminal


@router.get("/events/{event_id}", response_model=PlatformEvent)
async def get_platform_event(event_id: str, di: Di) -> PlatformEvent:
    context = get_context()
    if context is None:
        raise RuntimeError("get_platform_event requires request context")
    try:
        event = await di.bus_service.get_event(event_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"event {event_id} not found") from None
    _require_readable_snapshot(
        event,
        user_id=context.user.user_id,
        company_id=_require_active_company_id(context),
        not_found_detail=f"event {event_id} not found",
    )
    return event


def _require_active_company_id(context: Context) -> str:
    if context.active_company is None:
        raise HTTPException(status_code=403, detail="active company is required")
    return context.active_company.company_id


def _require_readable_snapshot(
    event: PlatformEvent,
    *,
    user_id: str,
    company_id: str,
    not_found_detail: str,
) -> None:
    if not _user_may_read_event(event, user_id=user_id):
        raise HTTPException(status_code=404, detail=not_found_detail)
    if event.company_id != company_id and event.company_id != "system":
        raise HTTPException(status_code=404, detail=not_found_detail)


def _user_may_read_event(event: PlatformEvent, *, user_id: str) -> bool:
    if event.meta.actor_user_id == user_id:
        return True
    if event.delivery is None:
        return False
    if event.delivery.user_ids is not None and user_id in event.delivery.user_ids:
        return True
    if event.delivery.company_id is not None:
        return True
    if event.delivery.broadcast:
        return True
    return False
