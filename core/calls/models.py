"""Базовые модели для WebRTC звонков."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

CallMode = Literal["p2p", "sfu"]

SignalType = Literal["offer", "answer", "ice_candidate"]


class TurnCredentials(BaseModel):
    """Временные TURN credentials для клиента (coturn REST API)."""

    username: str
    credential: str
    ttl: int
    uris: list[str]
