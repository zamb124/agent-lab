"""Тесты нормализации origin и Redis prefer-proxy для egress."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

import core.http.egress_route_preference as erp
from core.http.egress_route_preference import (
    egress_prefer_proxy_delete,
    egress_prefer_proxy_get,
    egress_prefer_proxy_set,
    normalized_http_origin,
    redis_key_for_origin,
)


@pytest.fixture(autouse=True)
def reset_egress_module_redis():
    erp._redis = None
    yield
    erp._redis = None


def _settings_with_proxy(*, redis_url: str, ttl: int = 120) -> MagicMock:
    s = MagicMock()
    s.database.redis_url = redis_url
    s.proxy.enabled = True
    s.proxy.proxies = ["http://127.0.0.1:9"]
    s.proxy.prefer_proxy_ttl_seconds = ttl
    return s


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://Example.COM/path", "https://example.com:443"),
        ("http://Api.Service:8080/v1", "http://api.service:8080"),
        ("HTTP://h:444/x", "http://h:444"),
    ],
)
def test_normalized_http_origin_ok(url: str, expected: str) -> None:
    assert normalized_http_origin(url) == expected


@pytest.mark.parametrize("bad", ["", "not-a-url", "/relative", "https://"])
def test_normalized_http_origin_invalid(bad: str) -> None:
    with pytest.raises(ValueError, match="absolute URL"):
        normalized_http_origin(bad)


def test_redis_key_for_origin() -> None:
    assert redis_key_for_origin("https://x:443").startswith(erp.REDIS_KEY_PREFIX)


@pytest.mark.asyncio
async def test_egress_prefer_proxy_get_false_without_proxy_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(erp, "_platform_proxy_configured", lambda: False)
    assert await egress_prefer_proxy_get("https://z:443") is False


@pytest.mark.asyncio
async def test_egress_prefer_proxy_set_skips_without_proxy_config(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_rc = MagicMock()
    mock_rc.set = AsyncMock()
    monkeypatch.setattr(erp, "_redis_client", lambda: mock_rc)
    monkeypatch.setattr(erp, "_platform_proxy_configured", lambda: False)
    await egress_prefer_proxy_set("https://z:443")
    mock_rc.set.assert_not_called()


@pytest.mark.asyncio
async def test_egress_prefer_proxy_set_warns_when_redis_set_false(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    mock_rc = MagicMock()
    mock_rc.set = AsyncMock(return_value=False)
    monkeypatch.setattr(erp, "_redis_client", lambda: mock_rc)
    monkeypatch.setattr(
        erp,
        "get_settings",
        lambda: _settings_with_proxy(redis_url="redis://localhost:63792/0"),
    )
    monkeypatch.setattr(erp, "_platform_proxy_configured", lambda: True)
    await egress_prefer_proxy_set("https://warn.example:443")
    mock_rc.set.assert_awaited_once()
    assert "SET failed" in caplog.text


@pytest.mark.asyncio
async def test_egress_prefer_proxy_roundtrip_real_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    redis_url = os.environ.get("DATABASE__REDIS_URL", "redis://localhost:63792/0")
    origin = "https://egress-test.invalid:443"
    key = redis_key_for_origin(origin)

    monkeypatch.setattr(
        erp,
        "get_settings",
        lambda: _settings_with_proxy(redis_url=redis_url, ttl=120),
    )

    rc = erp._redis_client()
    await rc.delete(key)
    assert await egress_prefer_proxy_get(origin) is False

    await egress_prefer_proxy_set(origin)
    assert await egress_prefer_proxy_get(origin) is True

    await egress_prefer_proxy_delete(origin)
    assert await egress_prefer_proxy_get(origin) is False


