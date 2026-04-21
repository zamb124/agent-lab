"""Redis presence для /sync/ws (без моков Redis)."""

from __future__ import annotations

import os
import uuid

import pytest


@pytest.mark.asyncio
async def test_sync_ws_presence_refresh_clear() -> None:
    url = os.environ.get("DATABASE__REDIS_URL")

    from apps.sync.ws_presence import (
        clear_sync_ws_presence,
        is_user_sync_ws_online,
        refresh_sync_ws_presence,
    )

    uid = f"sync_presence_{uuid.uuid4().hex[:12]}"
    await refresh_sync_ws_presence(url, uid)
    assert await is_user_sync_ws_online(url, uid) is True
    await clear_sync_ws_presence(url, uid)
    assert await is_user_sync_ws_online(url, uid) is False
