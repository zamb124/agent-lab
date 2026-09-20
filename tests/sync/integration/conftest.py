"""Фикстуры для integration-тестов Sync (op_*).

Все тесты используют реальные БД, Redis, TaskIQ. Никаких моков `op_*` или
репозиториев. Единственное явно разрешённое исключение — `webpush` к FCM/APN
в `test_sync_notification_delivery.py`.
"""


from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import pytest
import pytest_asyncio

from apps.sync.container import SyncContainer, get_sync_container
from core.config import get_settings, set_settings
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from tests.fixtures.auth import set_test_company_member_roles  # noqa: F401
from tests.fixtures.platform_events import platform_events_listener


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
    """Установить get_context() для in-process вызовов op_* (`require_company`)."""
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
    """Чтение шины `platform:events` в реальном Redis.

    Возвращает `receive(filter_type, timeout)` — собирает все события указанного
    типа за `timeout` секунд (после старта чтения). Используется так:

        async def test_op_X_publishes_push(redis_pubsub_listener, op_context, ...):
            await op_X(...)
            events = await redis_pubsub_listener("sync/space/created", timeout=2.0)
            assert events[0]["payload"]["message_id"] == "..."
    """
    async with platform_events_listener() as receive:

        async def _receive(filter_type: str, timeout: float = 2.0) -> list[dict[str, Any]]:
            return await receive(filter_type, None, timeout)

        yield _receive


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
