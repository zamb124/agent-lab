"""Фикстуры для integration-тестов Sync (op_*).

Все тесты используют реальные БД, Redis, TaskIQ. Никаких моков `op_*` или
репозиториев. Единственное явно разрешённое исключение — `webpush` к FCM/APN
в `test_sync_notification_delivery.py`.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import pytest
import pytest_asyncio
import redis.asyncio as redis_async

from apps.sync.container import SyncContainer, get_sync_container
from core.config import get_settings, set_settings
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import Company, User


@pytest.fixture()
def op_user(sync_user_id: str, company_id: str) -> User:
    """User-объект для прямого вызова `op_*` без HTTP/WS."""
    return User(
        user_id=sync_user_id,
        name="Sync test user",
        active_company_id=company_id,
        companies={company_id: ["owner", "admin"]},
    )


@pytest.fixture()
def op_user2(sync_user2_id: str, company_id: str) -> User:
    return User(
        user_id=sync_user2_id,
        name="Sync test user2",
        active_company_id=company_id,
        companies={company_id: ["member"]},
    )


@pytest.fixture()
def op_container() -> SyncContainer:
    return get_sync_container()


@pytest_asyncio.fixture()
async def op_context(
    sync_auth_token: str,  # обеспечивает создание company/user в shared
    company_id: str,
    op_user: User,
) -> AsyncIterator[None]:
    """Установить get_context() для in-process вызовов op_* (resolve_company_id)."""
    _ = sync_auth_token
    company = Company(
        company_id=company_id,
        name=f"Sync test {company_id}",
        owner_user_id=op_user.user_id,
        members={op_user.user_id: ["owner", "admin"]},
        balance=1000.0,
    )
    set_context(
        Context(
            user=op_user,
            active_company=company,
            user_companies=[company],
            channel="test",
            language=Language.RU,
        )
    )
    try:
        yield
    finally:
        clear_context()


PubSubReceive = Callable[[str, float], Awaitable[list[dict[str, Any]]]]


@pytest_asyncio.fixture()
async def redis_pubsub_listener() -> AsyncIterator[PubSubReceive]:
    """Подписка на канал `platform:ui_events` в реальном Redis.

    Возвращает `receive(filter_type, timeout)` — собирает все события указанного
    типа за `timeout` секунд (после старта подписки). Используется так:

        async def test_op_X_publishes_push(redis_pubsub_listener, op_context, ...):
            await op_X(...)
            events = await redis_pubsub_listener("sync/space/created", timeout=2.0)
            assert events[0]["payload"]["message_id"] == "..."
    """
    settings = get_settings()
    if not settings.database.redis_url:
        raise RuntimeError("database.redis_url не задан для redis_pubsub_listener.")

    client = redis_async.from_url(settings.database.redis_url)
    pubsub = client.pubsub()
    await pubsub.subscribe("platform:ui_events")
    # пропускаем подтверждение subscribe
    await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)

    async def _receive(filter_type: str, timeout: float = 2.0) -> list[dict[str, Any]]:
        """Собирает события указанного `type` из канала `platform:ui_events`.

        Формат конверта (см. `core.ui_events.dispatcher._envelope`):
            {"target": {...}, "event": {"id": ..., "type": ..., "payload": ...}}

        Возвращает уплощённый список событий с ключами `type` и `payload`,
        чтобы тесты могли обращаться к `e["payload"]` напрямую.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        collected: list[dict[str, Any]] = []
        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=min(remaining, 0.5))
            if msg is None:
                continue
            data = msg.get("data")
            if isinstance(data, (bytes, bytearray)):
                data = data.decode("utf-8")
            if not isinstance(data, str):
                continue
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            event = parsed.get("event")
            if not isinstance(event, dict):
                continue
            if event.get("type") == filter_type:
                collected.append(event)
        return collected

    try:
        yield _receive
    finally:
        await pubsub.unsubscribe("platform:ui_events")
        await pubsub.aclose()
        await client.aclose()


__all__ = [
    "_temporary_settings",
    "op_user",
    "op_user2",
    "op_container",
    "op_context",
    "redis_pubsub_listener",
    "s3_disabled_settings",
]


@asynccontextmanager
async def _temporary_settings(updated: dict[str, Any]) -> AsyncIterator[None]:
    """Временно подменить поля `BaseSettings` через `set_settings`, без monkeypatch.

    `updated` — dotted-path → value (e.g. {"s3.enabled": False}).
    """
    original = get_settings()
    snapshot = original.model_dump()

    def _apply(target: dict[str, object], dotted: str, value: object) -> None:
        parts = dotted.split(".")
        cursor: Any = target
        for key in parts[:-1]:
            if key not in cursor or not isinstance(cursor[key], dict):
                raise KeyError(f"_temporary_settings: путь {dotted!r} не существует в settings.")
            cursor = cursor[key]
        cursor[parts[-1]] = value

    patched = json.loads(json.dumps(snapshot))
    for dotted, value in updated.items():
        _apply(patched, dotted, value)

    new_settings = type(original).model_validate(patched)
    set_settings(new_settings)
    try:
        yield
    finally:
        set_settings(original)


@pytest_asyncio.fixture()
async def s3_disabled_settings() -> AsyncIterator[None]:
    """Временно выключает S3 в settings (fixture-runtime, без `monkeypatch`)."""
    async with _temporary_settings({"s3.enabled": False}):
        yield
