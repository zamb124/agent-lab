from __future__ import annotations

from typing import Any

import pytest

from apps.browser.engine.session_store import SessionStateStore
from apps.browser.engine.types import ContextSignature


class _FakeRedis:
    """In-memory двойник RedisClient для проверки контракта стора (Redis — внешняя граница)."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        _ = ttl
        self._data[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                removed += 1
        return removed


class _FakeContext:
    def __init__(self, *, storage_state: dict[str, Any]) -> None:
        self._storage_state = storage_state

    async def storage_state(self) -> dict[str, Any]:
        return dict(self._storage_state)


class _FakePage:
    def __init__(self, *, url: str, session_storage_dump: dict[str, str]) -> None:
        self.url = url
        self._session_storage_dump = dict(session_storage_dump)

    async def evaluate(self, script: str, arg: Any | None = None) -> Any:
        _ = script
        _ = arg
        return dict(self._session_storage_dump)


def _sig() -> ContextSignature:
    return ContextSignature(
        proxy_policy="http://proxy.local:3128",
        shared_storage_key="bucket-test",
        anti_bot_tier="white",
        stealth_init_version="v1",
        locale="en-US",
        timezone_id="UTC",
        user_agent="UA",
        page_mode="crawl",
        permissions_fingerprint="p",
    )


@pytest.mark.asyncio
async def test_session_state_store_put_get_delete_and_unknown_key_raises() -> None:
    store = SessionStateStore(redis_client=_FakeRedis(), ttl_sec=3600)  # pyright: ignore[reportArgumentType]
    sig = _sig()
    ctx = _FakeContext(storage_state={"cookies": [], "origins": []})
    page = _FakePage(url="https://example.com/a", session_storage_dump={"k": "v"})

    key = await store.capture_from(
        ctx,  # pyright: ignore[reportArgumentType]
        page,  # pyright: ignore[reportArgumentType]
        shared_storage_key="bucket-test",
        context_signature=sig,
        last_snapshot_ref=None,
    )

    blob = await store.get(key)
    assert blob.shared_storage_key == "bucket-test"
    assert blob.current_url == "https://example.com/a"
    assert blob.proxy_policy == sig.proxy_policy
    assert blob.locale == sig.locale
    assert blob.timezone_id == sig.timezone_id
    assert blob.user_agent == sig.user_agent
    assert blob.page_mode == sig.page_mode
    assert blob.permissions_fingerprint == sig.permissions_fingerprint
    assert blob.last_snapshot_ref is None
    assert blob.session_storage_by_origin["https://example.com"] == {"k": "v"}

    await store.delete(key)
    with pytest.raises(KeyError, match="Неизвестный state_key"):
        _ = await store.get(key)

    with pytest.raises(KeyError, match="Неизвестный state_key"):
        _ = await store.get("missing")
