"""Presence пользователей через HTTP API bus → Centrifugo."""

from __future__ import annotations

from core.clients.service_client import ServiceClient
from core.context import get_context
from core.internal_context_headers import build_internal_context_headers
from core.realtime.models import UserPresenceBatchResponse, UserPresenceSnapshot
from core.types import require_json_object


def _presence_headers(*, user_id: str, company_id: str | None) -> dict[str, str] | None:
    if get_context() is not None:
        return None
    if company_id is None or company_id == "":
        raise ValueError("company_id is required for presence without request context")
    return build_internal_context_headers(company_id=company_id, user_id=user_id)


async def fetch_user_presence(
    user_id: str,
    *,
    company_id: str | None = None,
) -> UserPresenceSnapshot:
    if not user_id:
        raise ValueError("user_id is required for presence")
    client = ServiceClient()
    headers = _presence_headers(user_id=user_id, company_id=company_id)
    if headers is None:
        payload = await client.get(
            "realtime",
            f"/realtime/api/v1/internal/presence/users/{user_id}",
        )
    else:
        payload = await client.get(
            "realtime",
            f"/realtime/api/v1/internal/presence/users/{user_id}",
            headers=headers,
        )
    return UserPresenceSnapshot.model_validate(
        require_json_object(payload, "realtime.presence.user")
    )


async def fetch_users_presence(
    user_ids: list[str],
    *,
    company_id: str | None = None,
) -> UserPresenceBatchResponse:
    if not user_ids:
        raise ValueError("user_ids is required for batch presence")
    client = ServiceClient()
    headers = _presence_headers(user_id=user_ids[0], company_id=company_id)
    if headers is None:
        payload = await client.post(
            "realtime",
            "/realtime/api/v1/internal/presence/users",
            json={"user_ids": user_ids},
        )
    else:
        payload = await client.post(
            "realtime",
            "/realtime/api/v1/internal/presence/users",
            json={"user_ids": user_ids},
            headers=headers,
        )
    return UserPresenceBatchResponse.model_validate(
        require_json_object(payload, "realtime.presence.batch")
    )


async def is_user_connected(user_id: str, *, company_id: str | None = None) -> bool:
    snapshot = await fetch_user_presence(user_id, company_id=company_id)
    return snapshot.connected
