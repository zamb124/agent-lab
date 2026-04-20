"""Realtime helpers для E2E-тестов sync (без моков).

Все вспомогательные функции работают против реального HTTP-сервера sync на
`127.0.0.1:9005` (фикстура `sync_service`) и реального Redis Pub/Sub. Никаких
`unittest.mock` / `AsyncMock` / `monkeypatch`.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable

from httpx import AsyncClient

from apps.sync.container import get_sync_container
from core.models.identity_models import Company, User
from core.utils.tokens import get_token_service


SYNC_BASE_URL = "http://127.0.0.1:9005"
SYNC_WS_URI = "ws://127.0.0.1:9005/sync/api/ws/notifications"


@asynccontextmanager
async def connect_ws(token: str) -> AsyncIterator[Any]:
    """Открывает WebSocket к /sync/api/ws/notifications с cookie-авторизацией.

    Импорт `websockets` локальный, чтобы тесты, не требующие WS, не тащили
    зависимость в коллекцию.
    """
    import websockets

    async with websockets.connect(
        SYNC_WS_URI,
        additional_headers=[("Cookie", f"auth_token={token}")],
    ) as ws:
        yield ws


async def wait_frame(
    ws: Any,
    *,
    type_: str,
    where: Callable[[dict[str, Any]], bool] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Ждёт фрейм с `type == type_` (и опциональным предикатом по payload).

    Каждый `recv` ограничен 2 секундами; общий deadline — `timeout`.
    Бросает `AssertionError` если за `timeout` ничего подходящего не пришло.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    last_seen: list[str] = []
    while asyncio.get_event_loop().time() < deadline:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 2.0))
        except asyncio.TimeoutError:
            continue
        parsed = json.loads(raw)
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
        return parsed
    raise AssertionError(
        f"wait_frame: за {timeout}s не получен фрейм type={type_!r}; "
        f"были типы: {last_seen}"
    )


async def assert_no_frame(
    ws: Any,
    *,
    type_: str,
    where: Callable[[dict[str, Any]], bool] | None = None,
    duration: float = 2.0,
) -> None:
    """Проверяет, что фрейм с `type == type_` НЕ пришёл за `duration` секунд."""
    deadline = asyncio.get_event_loop().time() + duration
    while asyncio.get_event_loop().time() < deadline:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            return
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 0.5))
        except asyncio.TimeoutError:
            continue
        parsed = json.loads(raw)
        if parsed.get("type") != type_:
            continue
        payload = parsed.get("payload")
        if where is not None:
            if not isinstance(payload, dict) or not where(payload):
                continue
        raise AssertionError(
            f"assert_no_frame: пришёл нежелательный фрейм type={type_!r}, payload={payload!r}"
        )


async def add_third_user(
    *,
    company_id: str,
    user_id: str,
    name: str = "Sync test user3",
) -> str:
    """Создаёт третьего пользователя в shared, добавляет в `Company.members`,
    возвращает свежий JWT токен.
    """
    container = get_sync_container()
    company = await container.company_repository.get(company_id)
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
    await container.company_repository.set(updated_company)
    user = User(
        user_id=user_id,
        name=name,
        emails=[f"{user_id}@test.local"],
        companies={company_id: ["member"]},
        active_company_id=company_id,
    )
    await container.user_repository.set(user)
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
