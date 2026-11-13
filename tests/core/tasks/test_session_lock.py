"""Тесты session-lock границы задачи на реальном Redis тестового стека.

Захват lock — внутри тела задачи через ``wrap_with_session_lock``/``session_lock``:
взаимное исключение по session_id, SessionLockTimeoutError как ошибка задачи,
release по токену владельца.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.tasks import session_lock as session_lock_module
from core.tasks.session_lock import (
    SessionLockTimeoutError,
    session_lock,
    wrap_with_session_lock,
)


def _session_id() -> str:
    return f"s-{uuid.uuid7().hex[:8]}"


@pytest.mark.asyncio
async def test_same_session_tasks_are_mutually_exclusive() -> None:
    """Второй захват ждёт release первого, затем получает lock."""
    session_id = _session_id()
    entered = asyncio.Event()
    second_entered = asyncio.Event()

    async def _hold() -> None:
        async with session_lock(session_id):
            entered.set()
            await asyncio.sleep(0.3)

    async def _second() -> None:
        async with session_lock(session_id):
            second_entered.set()

    holder = asyncio.create_task(_hold())
    await entered.wait()

    waiter = asyncio.create_task(_second())
    await asyncio.sleep(0.1)
    assert not second_entered.is_set(), "second task must wait for the session lock"

    await asyncio.wait_for(waiter, timeout=10)
    await holder


@pytest.mark.asyncio
async def test_lock_wait_timeout_fails_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Таймаут ожидания — SessionLockTimeoutError: без lock не исполняем."""
    session_id = _session_id()

    monkeypatch.setattr(session_lock_module, "LOCK_WAIT_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(session_lock_module, "LOCK_WAIT_INITIAL_MS", 20)
    monkeypatch.setattr(session_lock_module, "LOCK_WAIT_MAX_MS", 40)

    async with session_lock(session_id):
        with pytest.raises(SessionLockTimeoutError):
            async with session_lock(session_id):
                pytest.fail("lock body must not run without acquire")


@pytest.mark.asyncio
async def test_release_only_own_token() -> None:
    """Release по токену: истёкший и перехваченный lock не снимается."""
    session_id = _session_id()
    foreign_token = "foreign-worker"
    redis_client = RedisClient(get_settings().database.redis_url)
    await redis_client.connect()
    try:
        async with session_lock(session_id):
            # Имитируем истечение TTL и захват другим воркером.
            assert await redis_client.set(
                f"session_lock:{session_id}", foreign_token, ttl=300
            )
        # Чужой lock пережил release нашего владения.
        assert await redis_client.get(f"session_lock:{session_id}") == foreign_token
    finally:
        _ = await redis_client.delete(f"session_lock:{session_id}")
        await redis_client.close()


@pytest.mark.asyncio
async def test_normal_release_deletes_lock() -> None:
    session_id = _session_id()
    async with session_lock(session_id):
        pass

    redis_client = RedisClient(get_settings().database.redis_url)
    await redis_client.connect()
    try:
        assert await redis_client.get(f"session_lock:{session_id}") is None
    finally:
        await redis_client.close()


@pytest.mark.asyncio
async def test_wrapped_task_acquires_lock_for_kwarg_session_id() -> None:
    """Обёрнутая функция с параметром session_id исполняется под lock."""
    session_id = _session_id()
    observed: list[str] = []

    @wrap_with_session_lock
    async def _task(*, session_id: str) -> str:
        observed.append(session_id)
        return session_id

    # Пока lock занят извне, вызов ждёт release.
    async with session_lock(session_id):
        waiter = asyncio.create_task(_task(session_id=session_id))
        await asyncio.sleep(0.15)
        assert not waiter.done(), "task must wait for the session lock"
    result = await asyncio.wait_for(waiter, timeout=10)
    assert result == session_id
    assert observed == [session_id]


@pytest.mark.asyncio
async def test_wrapped_task_acquires_lock_for_positional_session_id() -> None:
    """Позиционный аргумент session_id тоже попадает под lock."""
    session_id = _session_id()

    @wrap_with_session_lock
    async def _task(flow_id: str, session_id: str) -> str:
        _ = flow_id
        return session_id

    async with session_lock(session_id):
        waiter = asyncio.create_task(_task("flow-1", session_id))
        await asyncio.sleep(0.15)
        assert not waiter.done(), "task must wait for the session lock"
    assert await asyncio.wait_for(waiter, timeout=10) == session_id


@pytest.mark.asyncio
async def test_wrapped_task_releases_lock_on_error() -> None:
    """Ошибка тела освобождает lock — сессия не блокируется навсегда."""
    session_id = _session_id()

    @wrap_with_session_lock
    async def _task(*, session_id: str) -> None:
        _ = session_id
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await _task(session_id=session_id)

    redis_client = RedisClient(get_settings().database.redis_url)
    await redis_client.connect()
    try:
        assert await redis_client.get(f"session_lock:{session_id}") is None
    finally:
        await redis_client.close()


def test_task_without_session_id_is_not_wrapped() -> None:
    async def _task(url: str) -> str:
        return url

    wrapped = wrap_with_session_lock(_task)
    assert wrapped is _task
