"""Контракты inbound Centrifugo и снимка presence."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from core.types import JsonObject, JsonValue


class BusProcessingState(StrEnum):
    RECEIVED = "received"
    DISPATCHED = "dispatched"
    PUBLISHED = "published"
    FAILED = "failed"
    DEADLINE_EXCEEDED = "deadline_exceeded"


class CentrifugoRpcInbound(BaseModel):
    """Тело HTTP RPC proxy Centrifugo → bus."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    client: str
    transport: str
    protocol: str
    encoding: str
    user: str
    method: str
    data: JsonValue = None
    meta: JsonObject | None = None


class CentrifugoRpcResult(BaseModel):
    data: JsonObject


class CentrifugoRpcResponse(BaseModel):
    result: CentrifugoRpcResult


class UserPresenceSnapshot(BaseModel):
    user_id: str
    connected: bool
    num_clients: int = Field(ge=0)


class UserPresenceBatchRequest(BaseModel):
    user_ids: list[str] = Field(min_length=1)


class UserPresenceBatchResponse(BaseModel):
    items: list[UserPresenceSnapshot]


class PresenceStatsResponse(BaseModel):
    online_users: int = Field(ge=0)
    active_channels: int = Field(ge=0)


class RealtimeCommandAccepted(BaseModel):
    accepted: bool
    event_id: str


class PlatformCommandEventPayload(BaseModel):
    """Payload `_requested` / `_succeeded` / `_failed` в каталоге шины."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")
