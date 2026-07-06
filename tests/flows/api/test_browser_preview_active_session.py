"""Browser preview: task-scoped active session endpoint."""

from __future__ import annotations

import pytest

from apps.flows.src.services.browser_preview import (
    browser_preview_active_session_key,
    create_browser_preview_token,
    get_active_browser_session_for_task,
)
from core.clients.redis_client import RedisClient
from core.config import get_settings


@pytest.mark.asyncio
async def test_active_session_returns_urls_when_redis_has_session(
    flows_client,
    unique_id: str,
) -> None:
    task_id = f"task-{unique_id}"
    session_id = f"sess-{unique_id}"
    token = create_browser_preview_token(session_id=session_id, task_id=task_id)

    redis = RedisClient(get_settings().database.redis_url)
    key = browser_preview_active_session_key(task_id)
    _ = await redis.set(key, session_id, ttl=300)

    try:
        response = await flows_client.get(
            f"/flows/api/v1/browser-preview/tasks/{task_id}/active-session",
            params={"token": token},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["session_id"] == session_id
        assert isinstance(payload["viewer_url"], str)
        assert session_id in payload["viewer_url"]
        assert isinstance(payload["screenshot_url"], str)
        assert isinstance(payload["status_url"], str)
    finally:
        _ = await redis.delete(key)


@pytest.mark.asyncio
async def test_active_session_returns_null_without_redis_entry(
    flows_client,
    unique_id: str,
) -> None:
    task_id = f"task-{unique_id}"
    session_id = f"sess-{unique_id}"
    token = create_browser_preview_token(session_id=session_id, task_id=task_id)

    response = await flows_client.get(
        f"/flows/api/v1/browser-preview/tasks/{task_id}/active-session",
        params={"token": token},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] is None
    assert payload["viewer_url"] is None


@pytest.mark.asyncio
async def test_active_session_rejects_token_for_other_task(
    flows_client,
    unique_id: str,
) -> None:
    task_id = f"task-{unique_id}"
    other_task_id = f"task-other-{unique_id}"
    session_id = f"sess-{unique_id}"
    token = create_browser_preview_token(session_id=session_id, task_id=task_id)

    response = await flows_client.get(
        f"/flows/api/v1/browser-preview/tasks/{other_task_id}/active-session",
        params={"token": token},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_active_browser_session_for_task_reads_redis(unique_id: str) -> None:
    task_id = f"task-read-{unique_id}"
    session_id = f"sess-read-{unique_id}"
    redis = RedisClient(get_settings().database.redis_url)
    key = browser_preview_active_session_key(task_id)
    _ = await redis.set(key, session_id, ttl=300)
    try:
        loaded = await get_active_browser_session_for_task(task_id)
        assert loaded == session_id
    finally:
        _ = await redis.delete(key)
