"""Sweeper Granian: просроченный *_requested → *_failed deadline_exceeded."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx2 import AsyncClient

from apps.realtime.services.bus_service import RealtimeBusService
from core.events.contract import EventDelivery, PlatformEvent, PlatformEventMeta
from core.realtime.models import BusProcessingState
from tests.realtime.centrifugo_ws import connect_centrifugo, wait_platform_event


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_sweeper_publishes_deadline_exceeded(
    realtime_event_log: RealtimeBusService,
    realtime_session_client: AsyncClient,
    auth_token_system: str,
    system_user_id: str,
    unique_id: str,
) -> None:
    event_id = f"e_sweep_{unique_id}"
    command = PlatformEvent(
        event_id=event_id,
        type="sync/channels/create_requested",
        company_id="system",
        payload={"name": f"sweep-{unique_id}"},
        meta=PlatformEventMeta(source="ws", actor_user_id=system_user_id),
        delivery=EventDelivery(user_ids=[system_user_id]),
    )
    async with connect_centrifugo(auth_token_system) as ws:
        inserted = await realtime_event_log.insert_if_absent(
            command,
            processing_state=BusProcessingState.DISPATCHED,
            owner_service="sync",
            deadline_at=datetime.now(timezone.utc) - timedelta(seconds=2),
        )
        if not inserted:
            raise AssertionError(f"sweep command {event_id} already existed")
        failed = await wait_platform_event(
            ws,
            type_="sync/channels/create_failed",
            meta_where={"causation_id": event_id},
            timeout=20.0,
        )
        meta = failed.get("meta")
        if not isinstance(meta, dict):
            raise AssertionError("deadline fail meta must be object")
        assert meta.get("causation_id") == event_id
        payload = failed.get("payload")
        if not isinstance(payload, dict):
            raise AssertionError("deadline fail payload must be object")
        assert payload.get("error_code") == "deadline_exceeded"
        terminal = await realtime_session_client.get(
            f"/realtime/api/v1/events/{event_id}/terminal"
        )
        assert terminal.status_code == 200, terminal.text
        assert terminal.json()["payload"]["error_code"] == "deadline_exceeded"
        command_row = await realtime_session_client.get(f"/realtime/api/v1/events/{event_id}")
        assert command_row.status_code == 200, command_row.text
        assert command_row.json()["type"] == "sync/channels/create_requested"
