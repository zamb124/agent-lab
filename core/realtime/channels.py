"""Каналы Centrifugo и SESSION JWT claims для user WS."""

from __future__ import annotations

from core.events.contract import EventDelivery

SESSION_JWT_ISSUER = "platform.session"
BROADCAST_CHANNEL = "broadcast"


def user_channel(user_id: str) -> str:
    if not user_id:
        raise ValueError("user_id is required for Centrifugo user channel")
    return f"user:{user_id}"


def company_channel(company_id: str) -> str:
    if not company_id:
        raise ValueError("company_id is required for Centrifugo company channel")
    return f"company:{company_id}"


def session_jwt_channels(user_id: str, company_id: str) -> list[str]:
    """Server-side subscriptions в connection JWT (claim `channels`)."""
    if not user_id:
        raise ValueError("user_id is required for SESSION JWT channels")
    channels = [user_channel(user_id), BROADCAST_CHANNEL]
    if company_id:
        channels.insert(1, company_channel(company_id))
    return channels


def session_jwt_meta(company_id: str) -> dict[str, str]:
    return {"company_id": company_id}


def centrifugo_channels_for_delivery(delivery: EventDelivery) -> list[str]:
    delivery.assert_valid()
    if delivery.broadcast:
        return [BROADCAST_CHANNEL]
    if delivery.company_id is not None:
        return [company_channel(delivery.company_id)]
    if delivery.user_ids is None:
        raise ValueError("EventDelivery.user_ids is required when not company/broadcast")
    return [user_channel(user_id) for user_id in delivery.user_ids]
