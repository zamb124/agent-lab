"""Отправка PlatformEvent в bus: process-local ingest или HTTP на realtime."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from core.clients.service_client import ServiceClient
from core.context import get_context
from core.events.contract import PlatformEvent
from core.internal_context_headers import build_internal_context_headers
from core.types import require_json_object

LocalEventIngest = Callable[[PlatformEvent], Awaitable[PlatformEvent]]

_local_ingest: LocalEventIngest | None = None

PLATFORM_EVENT_SUBMIT_USER_ID = "platform.event.publisher"


def _submit_headers(event: PlatformEvent) -> dict[str, str] | None:
    if get_context() is not None:
        return None
    if not event.company_id:
        raise ValueError("PlatformEvent.company_id is required to submit without request context")
    return build_internal_context_headers(
        company_id=event.company_id,
        user_id=PLATFORM_EVENT_SUBMIT_USER_ID,
    )


def bind_local_event_ingest(handler: LocalEventIngest) -> None:
    """Привязать ingest текущего процесса (lifespan realtime / pytest)."""
    global _local_ingest
    if _local_ingest is not None:
        raise RuntimeError("local PlatformEvent ingest is already bound")
    _local_ingest = handler


def unbind_local_event_ingest() -> None:
    global _local_ingest
    _local_ingest = None


def local_event_ingest_bound() -> bool:
    return _local_ingest is not None


async def submit_platform_event(event: PlatformEvent) -> PlatformEvent:
    """Persist+XADD+CF через bus. Повтор того же event_id возвращает снимок как есть."""
    if _local_ingest is not None:
        return await _local_ingest(event)
    client = ServiceClient()
    headers = _submit_headers(event)
    if headers is None:
        response_payload = await client.post(
            "realtime",
            "/realtime/api/v1/internal/events",
            json=event.model_dump(mode="json"),
        )
    else:
        response_payload = await client.post(
            "realtime",
            "/realtime/api/v1/internal/events",
            json=event.model_dump(mode="json"),
            headers=headers,
        )
    return PlatformEvent.model_validate(
        require_json_object(response_payload, "realtime.internal.events")
    )
