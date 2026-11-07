"""Presence через HTTP API Centrifugo."""

from __future__ import annotations

from fastapi import APIRouter

from core.realtime.centrifugo_client import centrifugo_channels, centrifugo_presence_stats
from core.realtime.channels import user_channel
from core.realtime.models import (
    PresenceStatsResponse,
    UserPresenceBatchRequest,
    UserPresenceBatchResponse,
    UserPresenceSnapshot,
)
from core.types import require_json_object

router = APIRouter()


@router.get("/internal/presence/users/{user_id}", response_model=UserPresenceSnapshot)
async def get_user_presence(user_id: str) -> UserPresenceSnapshot:
    return await centrifugo_presence_stats(user_channel(user_id))


@router.get("/internal/presence/stats", response_model=PresenceStatsResponse)
async def get_presence_stats() -> PresenceStatsResponse:
    result = await centrifugo_channels()
    channels_value = result.get("channels")
    channels = {} if channels_value is None else require_json_object(channels_value, "centrifugo.channels.channels")
    online_users = sum(1 for name in channels if name.startswith("user:"))
    return PresenceStatsResponse(online_users=online_users, active_channels=len(channels))


@router.post("/internal/presence/users", response_model=UserPresenceBatchResponse)
async def batch_user_presence(
    request_body: UserPresenceBatchRequest,
) -> UserPresenceBatchResponse:
    items: list[UserPresenceSnapshot] = []
    for user_id in request_body.user_ids:
        items.append(await centrifugo_presence_stats(user_channel(user_id)))
    return UserPresenceBatchResponse(items=items)
