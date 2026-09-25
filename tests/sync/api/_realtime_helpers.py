"""Хелперы realtime для E2E-тестов sync (без моков).

HTTP — `127.0.0.1:9005`. User WS — Centrifugo JSON protocol
(`CENTRIFUGO_WS_URL`), кадр = PlatformEvent.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from httpx import AsyncClient

from core.authz.company_sync import sync_company_member_roles
from core.models.identity_models import Company, User
from core.realtime.presence import is_user_connected
from core.types import JsonObject, require_json_object
from core.utils.tokens import get_token_service
from tests.realtime.centrifugo_ws import (
    CentrifugoWsClient,
    connect_centrifugo,
    rpc_platform_event,
)

SYNC_BASE_URL = "http://127.0.0.1:9005"
FRONTEND_BASE_URL = "http://127.0.0.1:9004"


@asynccontextmanager
async def connect_ws(token: str) -> AsyncIterator[CentrifugoWsClient]:
    async with connect_centrifugo(token) as client:
        yield client


async def wait_sync_ws_online(
    user_id: str,
    *,
    company_id: str,
    timeout: float = 10.0,
) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if await is_user_connected(user_id, company_id=company_id):
            return
        await asyncio.sleep(0.05)
    raise AssertionError(
        f"wait_sync_ws_online: user {user_id!r} не появился в Centrifugo presence за {timeout}s"
    )


async def wait_sync_ws_offline(
    user_id: str,
    *,
    company_id: str,
    timeout: float = 10.0,
) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if not await is_user_connected(user_id, company_id=company_id):
            return
        await asyncio.sleep(0.05)
    raise AssertionError(
        f"wait_sync_ws_offline: user {user_id!r} всё ещё в Centrifugo presence за {timeout}s"
    )


async def wait_frame(
    ws: CentrifugoWsClient,
    *,
    type_: str,
    where: Callable[[dict[str, Any]], bool] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    deadline = asyncio.get_event_loop().time() + timeout
    last_seen: list[str] = []
    while asyncio.get_event_loop().time() < deadline:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            break
        try:
            parsed = await ws.recv_platform_event(timeout=min(remaining, 2.0))
        except asyncio.TimeoutError:
            continue
        frame_type = parsed.get("type")
        if not isinstance(frame_type, str):
            continue
        last_seen.append(frame_type)
        if frame_type != type_:
            continue
        payload = parsed.get("payload")
        if where is not None:
            if not isinstance(payload, dict):
                continue
            if not where(payload):
                continue
        return dict(parsed)
    raise AssertionError(
        f"wait_frame: за {timeout}s не получен фрейм type={type_!r}; "
        f"были типы: {last_seen}"
    )


async def assert_no_frame(
    ws: CentrifugoWsClient,
    *,
    type_: str,
    where: Callable[[dict[str, Any]], bool] | None = None,
    duration: float = 2.0,
) -> None:
    deadline = asyncio.get_event_loop().time() + duration
    while asyncio.get_event_loop().time() < deadline:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            return
        try:
            parsed = await ws.recv_platform_event(timeout=min(remaining, 0.5))
        except asyncio.TimeoutError:
            continue
        if parsed.get("type") != type_:
            continue
        payload = parsed.get("payload")
        if where is not None:
            if not isinstance(payload, dict) or not where(payload):
                continue
        raise AssertionError(
            f"assert_no_frame: пришёл нежелательный фрейм type={type_!r}, payload={payload!r}"
        )


async def send_ws_command(
    ws: CentrifugoWsClient,
    *,
    token: str,
    event_type: str,
    payload: JsonObject,
    event_id: str,
) -> JsonObject:
    token_data = get_token_service().validate_token(token)
    if token_data is None:
        raise AssertionError("SESSION JWT is required for Centrifugo RPC")
    return await rpc_platform_event(
        ws,
        event_type=event_type,
        payload=payload,
        company_id=token_data.company_id,
        event_id=event_id,
    )


async def add_third_user(
    *,
    company_id: str,
    user_id: str,
    name: str = "Sync test user3",
) -> str:
    """Создаёт третьего пользователя в shared, dual-write membership в OpenFGA,
    возвращает свежий JWT токен.
    """
    from tests.sync.conftest import require_sync_di

    di = require_sync_di()
    company = await Company.get(company_id)
    if company is None:
        raise AssertionError(
            f"add_third_user: company {company_id!r} ещё не создана; "
            "убедись, что в тесте используется фикстура `sync_auth_token`."
        )
    members = dict(company.members)
    members[user_id] = ["member"]
    updated_company = Company(
        company_id=company.company_id,
        name=company.name,
        owner_user_id=company.owner_user_id,
        members=members,
        balance=company.balance,
    )
    await Company.set(updated_company)
    user = User(
        user_id=user_id,
        name=name,
        emails=[f"{user_id}@test.local"],
        companies={company_id: ["member"]},
        active_company_id=company_id,
    )
    await User.set(user)
    await sync_company_member_roles(
        di.authz_service,
        company_id=company_id,
        user_id=user_id,
        roles=["member"],
    )
    token_service = get_token_service()
    return token_service.create_token(user_id, company_id=company_id)


async def add_member_via_http(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    channel_id: str,
    user_id: str,
    role: str = "member",
) -> None:
    """REST-обёртка добавления участника канала."""
    r = await client.post(
        f"/sync/api/v1/channels/{channel_id}/members",
        headers=headers,
        json={"user_id": user_id, "role": role},
    )
    if r.status_code not in (200, 201):
        raise AssertionError(
            f"add_member_via_http: POST members вернул {r.status_code}: {r.text}"
        )


async def send_text_message(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    channel_id: str,
    text: str,
    parent_message_id: str | None = None,
    mentioned_user_ids: list[str] | None = None,
) -> dict[str, Any]:
    """REST-обёртка отправки текстового сообщения."""
    body: dict[str, Any] = {
        "thread_id": None,
        "parent_message_id": parent_message_id,
        "contents": [
            {"type": "text/plain", "order": 0, "data": {"body": text}},
        ],
    }
    if mentioned_user_ids is not None:
        body["mentioned_user_ids"] = mentioned_user_ids
    r = await client.post(
        f"/sync/api/v1/channels/{channel_id}/messages",
        headers=headers,
        json=body,
    )
    if r.status_code != 201:
        raise AssertionError(
            f"send_text_message: POST messages вернул {r.status_code}: {r.text}"
        )
    return r.json()


PubSubReceive = Callable[[str, float], Awaitable[list[dict[str, Any]]]]


@asynccontextmanager
async def http_owner(token: str) -> AsyncIterator[AsyncClient]:
    """`AsyncClient` к sync_service с готовыми Bearer-заголовками."""
    async with AsyncClient(base_url=SYNC_BASE_URL, timeout=60.0) as client:
        client.headers.update({"Authorization": f"Bearer {token}"})
        yield client


@asynccontextmanager
async def http_frontend(token: str) -> AsyncIterator[AsyncClient]:
    """`AsyncClient` к frontend_service для Files API."""
    async with AsyncClient(base_url=FRONTEND_BASE_URL, timeout=60.0) as client:
        client.headers.update({"Authorization": f"Bearer {token}"})
        yield client


def require_payload_object(event: dict[str, Any]) -> dict[str, Any]:
    return dict(require_json_object(event.get("payload"), "platform_event.payload"))
