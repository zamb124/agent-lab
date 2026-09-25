"""Presence через HTTP API Centrifugo."""

from __future__ import annotations

from fastapi import APIRouter

from core.realtime.centrifugo_client import centrifugo_presence_stats
from core.realtime.channels import user_channel
from core.realtime.models import (
    UserPresenceBatchRequest,
    UserPresenceBatchResponse,
    UserPresenceSnapshot,
)

router = APIRouter()


@router.get("/internal/presence/users/{user_id}", response_model=UserPresenceSnapshot)
async def get_user_presence(user_id: str) -> UserPresenceSnapshot:
    return await centrifugo_presence_stats(user_channel(user_id))


@router.post("/internal/presence/users", response_model=UserPresenceBatchResponse)
async def batch_user_presence(
    request_body: UserPresenceBatchRequest,
) -> UserPresenceBatchResponse:
    items: list[UserPresenceSnapshot] = []
    for user_id in request_body.user_ids:
        items.append(await centrifugo_presence_stats(user_channel(user_id)))
    return UserPresenceBatchResponse(items=items)
