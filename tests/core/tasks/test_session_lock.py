"""Тесты `SessionLockMiddleware` на реальном Redis тестового стека.

Проверяют: взаимное исключение по session_id, ошибку при таймауте ожидания
(задача без lock не исполняется), release по токену владельца.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from taskiq import TaskiqMessage, TaskiqResult

from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.tasks import session_lock as session_lock_module
from core.tasks.session_lock import (
    SessionLockMiddleware,
    SessionLockTimeoutError,
)


def _message(session_id: str) -> TaskiqMessage:
    return TaskiqMessage(
        task_id=uuid.uuid7().hex,
        task_name="test/task",
        labels={},
        labels_types=None,
        args=[],
        kwargs={"session_id": session_id},
    )


def _result() -> TaskiqResult[None]:
    return TaskiqResult(
        is_err=False,
        log=None,
        return_value=None,
        execution_time=0.0,
        labels={},
    )


@pytest.mark.asyncio
async def test_same_session_tasks_are_mutually_exclusive() -> None:
    """Второй pre_execute ждёт release первого, затем захватывает lock."""
    middleware = SessionLockMiddleware(queue_name="test_queue")
    session_id = f"s-{uuid.uuid7().hex[:8]}"
    first, second = _message(session_id), _message(session_id)

    await middleware.pre_execute(first)
    wait_started = asyncio.Event()

    async def second_pre() -> TaskiqMessage:
        wait_started.set()
        return await middleware.pre_execute(second)

    waiter = asyncio.create_task(second_pre())
    await wait_started.wait()
    await asyncio.sleep(0.15)
    assert not waiter.done(), "second task must wait for the session lock"

    await middleware.post_execute(first, _result())
    await asyncio.wait_for(waiter, timeout=10)

    await middleware.post_execute(second, _result())


@pytest.mark.asyncio
async def test_lock_wait_timeout_fails_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Таймаут ожидания — SessionLockTimeoutError: без lock не исполняем."""
    middleware = SessionLockMiddleware(queue_name="test_queue")
    session_id = f"s-{uuid.uuid7().hex[:8]}"
    first = _message(session_id)
    await middleware.pre_execute(first)

    monkeypatch.setattr(session_lock_module, "LOCK_WAIT_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(session_lock_module, "LOCK_WAIT_INITIAL_MS", 20)
    monkeypatch.setattr(session_lock_module, "LOCK_WAIT_MAX_MS", 40)
    try:
        with pytest.raises(SessionLockTimeoutError):
            await middleware.pre_execute(_message(session_id))
    finally:
        await middleware.post_execute(first, _result())


@pytest.mark.asyncio
async def test_release_only_own_token() -> None:
    """Release по токену: истёкший и перехваченный lock не снимается."""
    middleware = SessionLockMiddleware(queue_name="test_queue")
    session_id = f"s-{uuid.uuid7().hex[:8]}"
    message = _message(session_id)
    await middleware.pre_execute(message)

    redis_client = RedisClient(get_settings().database.redis_url)
    await redis_client.connect()
    lock_key = f"session_lock:{session_id}"
    foreign_token = "foreign-worker"
    # Имитируем истечение TTL и захват другим воркером.
    assert await redis_client.set(lock_key, foreign_token, ttl=300)
    try:
        await middleware.post_execute(message, _result())
        # Чужой lock цел.
        assert await redis_client.get(lock_key) == foreign_token
    finally:
        _ = await redis_client.delete(lock_key)
        await redis_client.close()


@pytest.mark.asyncio
async def test_normal_release_deletes_lock() -> None:
    middleware = SessionLockMiddleware(queue_name="test_queue")
    session_id = f"s-{uuid.uuid7().hex[:8]}"
    message = _message(session_id)
    await middleware.pre_execute(message)
    await middleware.post_execute(message, _result())

    redis_client = RedisClient(get_settings().database.redis_url)
    await redis_client.connect()
    try:
        assert await redis_client.get(f"session_lock:{session_id}") is None
    finally:
        await redis_client.close()


@pytest.mark.asyncio
async def test_task_without_session_id_passes() -> None:
    middleware = SessionLockMiddleware(queue_name="test_queue")
    message = TaskiqMessage(
        task_id=uuid.uuid7().hex,
        task_name="test/task",
        labels={},
        labels_types=None,
        args=[],
        kwargs={},
    )
    out = await middleware.pre_execute(message)
    assert out is message
