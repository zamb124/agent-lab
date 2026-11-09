"""Интеграционные тесты SmartProxyClient/stream/oauth с MockTransport и точечными monkeypatch."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import cast
from unittest.mock import MagicMock, PropertyMock

import httpx2
import pytest

from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.http.client import (
    ProxyStrategy,
    SmartProxyClient,
    _request_direct_burst,
    _retry_http_statuses_for_smart,
    get_httpx_client,
    request_public_oauth,
)
from core.http.egress_route_preference import (
    egress_prefer_proxy_delete,
    egress_prefer_proxy_get,
    egress_prefer_proxy_set,
    normalized_http_origin,
    redis_key_for_origin,
)
from tests.core.http_proxy_helpers import (
    ClosedCallResponse,
    install_mock_httpx_client,
    unread_json_response,
)


def _proxy_settings(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock_settings = MagicMock()
    mock_settings.proxy.get_next_proxy.return_value = "http://127.0.0.1:9"
    mock_settings.proxy.connect_timeout = 15.0
    mock_settings.proxy.mark_last_proxy_failed = MagicMock()
    monkeypatch.setattr("core.http.client.SmartProxyClient._get_settings", lambda self: mock_settings)
    return mock_settings


@asynccontextmanager
async def _prefer_proxy_origin(monkeypatch: pytest.MonkeyPatch, url: str) -> AsyncIterator[None]:
    proxy = get_settings().proxy
    monkeypatch.setattr(proxy, "enabled", True)
    if not proxy.proxies:
        monkeypatch.setattr(proxy, "proxies", ["http://127.0.0.1:9"])
    origin = normalized_http_origin(url)
    await egress_prefer_proxy_set(origin)
    try:
        yield
    finally:
        await egress_prefer_proxy_delete(origin)


async def _stamp_prefer_marker(url: str, marker: str, *, ttl: int = 120) -> None:
    redis = RedisClient(get_settings().database.redis_url)
    await redis.set(redis_key_for_origin(normalized_http_origin(url)), marker, ttl=ttl)


async def _prefer_ttl(url: str) -> int:
    redis = RedisClient(get_settings().database.redis_url)
    return await redis.ttl(redis_key_for_origin(normalized_http_origin(url)))


def _enable_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    proxy = get_settings().proxy
    monkeypatch.setattr(proxy, "enabled", True)
    if not proxy.proxies:
        monkeypatch.setattr(proxy, "proxies", ["http://127.0.0.1:9"])


def _force_proxy(monkeypatch: pytest.MonkeyPatch, proxy_url: str) -> None:
    proxy = get_settings().proxy
    monkeypatch.setattr(proxy, "enabled", True)
    monkeypatch.setattr(proxy, "proxies", [proxy_url])
    monkeypatch.setattr(proxy, "connect_timeout", 0.2)


@asynccontextmanager
async def _serve_http(host: str, status_code: int, body: bytes) -> AsyncIterator[int]:
    reason = "OK" if status_code == 200 else "Service Unavailable"

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b""):
                break
        head = (
            f"HTTP/1.1 {status_code} {reason}\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode()
        writer.write(head + body)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle, host, 0)
    sockets = server.sockets
    if sockets is None or len(sockets) == 0:
        server.close()
        await server.wait_closed()
        raise RuntimeError("http test listener has no socket")
    port = int(sockets[0].getsockname()[1])
    try:
        yield port
    finally:
        server.close()
        await server.wait_closed()


def test_retry_http_statuses_includes_401_when_proxy_setting_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gs = MagicMock()
    gs.proxy.retry_http_401_via_proxy = True
    monkeypatch.setattr("core.http.client.get_settings", lambda: gs)
    assert 401 in _retry_http_statuses_for_smart()


@pytest.mark.asyncio
async def test_request_direct_burst_all_fail_reraises_last_connect_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx2.Request) -> None:
        raise httpx2.ConnectError("burst", request=request)

    install_mock_httpx_client(
        monkeypatch,
        cast(Callable[[httpx2.Request], httpx2.Response], handler),
    )
    with pytest.raises(httpx2.ConnectError, match="burst"):
        await _request_direct_burst("GET", "https://burst.example/x", timeout=1.0, attempts=2)


@pytest.mark.asyncio
async def test_request_direct_burst_zero_attempts_raises() -> None:
    with pytest.raises(RuntimeError, match="attempts must be"):
        await _request_direct_burst("GET", "https://x.test/z", timeout=1.0, attempts=0)


@pytest.mark.asyncio
async def test_relative_path_resolves_with_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mock_httpx_client(monkeypatch, lambda r: httpx2.Response(200))
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART, base_url="https://api.example") as client:
        r = await client.request("GET", "/v1/r")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_smart_connect_failure_raises_when_proxy_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx2.Request) -> None:
        raise httpx2.ConnectError("x", request=request)

    install_mock_httpx_client(
        monkeypatch,
        cast(Callable[[httpx2.Request], httpx2.Response], handler),
    )
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: False)
    with pytest.raises(httpx2.ConnectError):
        async with get_httpx_client(strategy=ProxyStrategy.SMART) as client:
            await client.request("GET", "https://no-proxy-fail.example/y")


@pytest.mark.asyncio
async def test_stream_smart_connect_failure_raises_when_proxy_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StreamFail:
        async def __aenter__(self) -> object:
            raise httpx2.ConnectError("s", request=httpx2.Request("GET", "https://x"))

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def aclose(self) -> None:
            return None

        def stream(self, method: str, url: str, **kwargs: object) -> StreamFail:
            return StreamFail()

    monkeypatch.setattr("core.http.client.httpx2.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: False)
    with pytest.raises(httpx2.ConnectError):
        async with get_httpx_client(strategy=ProxyStrategy.SMART) as client:
            async with client.stream("GET", "https://stream-no-proxy.example/s"):
                pass


@pytest.mark.asyncio
async def test_stream_direct_first_local(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mock_httpx_client(monkeypatch, lambda r: httpx2.Response(201))
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.DIRECT_FIRST) as client:
        async with client.stream("GET", "http://127.0.0.1:8010/df") as resp:
            assert resp.status_code == 201


@pytest.mark.asyncio
async def test_stream_direct_first_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mock_httpx_client(monkeypatch, lambda r: httpx2.Response(200))
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.DIRECT_FIRST) as client:
        async with client.stream("GET", "https://df-remote.example/s") as resp:
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_http_method_shortcuts(monkeypatch: pytest.MonkeyPatch) -> None:
    methods: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        methods.append(request.method)
        return httpx2.Response(200)

    install_mock_httpx_client(
        monkeypatch,
        cast(Callable[[httpx2.Request], httpx2.Response], handler),
    )
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        await client.get("https://m.example/g")
        await client.post("https://m.example/p")
        await client.put("https://m.example/u")
        await client.delete("https://m.example/d")
        await client.patch("https://m.example/a")
    assert methods == ["GET", "POST", "PUT", "DELETE", "PATCH"]


@pytest.mark.asyncio
async def test_smart_proxy_client_aclose_inner_client() -> None:
    inner = httpx2.AsyncClient()
    client = get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART)
    client._client = inner
    await client.aclose()
    assert inner.is_closed
    assert client._client is None


@pytest.mark.asyncio
async def test_smart_proxy_client_aexit_closes_inner_client() -> None:
    inner = httpx2.AsyncClient()
    client = get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART)
    client._client = inner
    async with client:
        pass
    assert inner.is_closed
    assert client._client is None


def test_get_settings_cached_on_smart_client() -> None:
    client = SmartProxyClient(timeout=5.0, use_proxy=False)
    first = client._get_settings()
    second = client._get_settings()
    assert first is second


@pytest.mark.asyncio
async def test_stream_prefer_sticky_success_calls_set(monkeypatch: pytest.MonkeyPatch) -> None:
    class StreamOk:
        async def __aenter__(self) -> httpx2.Response:
            return httpx2.Response(200)

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            _ = kwargs.get("proxy")

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def aclose(self) -> None:
            return None

        def stream(self, method: str, url: str, **kwargs: object) -> StreamOk:
            return StreamOk()

    monkeypatch.setattr("core.http.client.httpx2.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    _proxy_settings(monkeypatch)
    async with _prefer_proxy_origin(monkeypatch, "https://sticky-ok.example/s"):
        await _stamp_prefer_marker("https://sticky-ok.example/s", "1", ttl=60)
        async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
            async with client.stream("GET", "https://sticky-ok.example/s") as resp:
                assert resp.status_code == 200
        assert await _prefer_ttl("https://sticky-ok.example/s") > 60


@pytest.mark.asyncio
async def test_stream_prefer_zero_retries_raises_unexpected_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(SmartProxyClient, "MAX_PROXY_RETRIES", 0)
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    _proxy_settings(monkeypatch)
    with pytest.raises(RuntimeError, match="unexpected state"):
        async with _prefer_proxy_origin(monkeypatch, "https://sticky-zero.example/s"):
            async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
                async with client.stream("GET", "https://sticky-zero.example/s"):
                    pass


@pytest.mark.asyncio
async def test_stream_403_proxy_phase_all_connect_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    class Direct403:
        async def __aenter__(self) -> httpx2.Response:
            return httpx2.Response(403)

        async def __aexit__(self, *args: object) -> None:
            return None

    class ProxyFail:
        async def __aenter__(self) -> object:
            raise httpx2.ConnectError("px", request=httpx2.Request("GET", "https://x"))

        async def __aexit__(self, *args: object) -> None:
            return None

    phase = {"direct": True}

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._proxy_kw = kwargs.get("proxy")

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def aclose(self) -> None:
            return None

        def stream(self, method: str, url: str, **kwargs: object) -> Direct403 | ProxyFail:
            if self._proxy_kw is None and phase["direct"]:
                phase["direct"] = False
                return Direct403()
            return ProxyFail()

    _proxy_settings(monkeypatch)
    monkeypatch.setattr("core.http.client.httpx2.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    with pytest.raises(httpx2.ConnectError):
        async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
            async with client.stream("GET", "https://stream-403-dead.example/s"):
                pass


@pytest.mark.asyncio
async def test_stream_proxy_only_all_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    class AlwaysFail:
        async def __aenter__(self) -> object:
            raise httpx2.ConnectError("p", request=httpx2.Request("GET", "https://x"))

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def aclose(self) -> None:
            return None

        def stream(self, method: str, url: str, **kwargs: object) -> AlwaysFail:
            return AlwaysFail()

    _proxy_settings(monkeypatch)
    monkeypatch.setattr("core.http.client.httpx2.AsyncClient", FakeAsyncClient)
    with pytest.raises(httpx2.ConnectError):
        async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.PROXY_ONLY) as client:
            async with client.stream("GET", "https://p-only-dead.example/s"):
                pass


@pytest.mark.asyncio
async def test_stream_context_aexit_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mock_httpx_client(monkeypatch, lambda r: httpx2.Response(200))
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        stream_cm = client.stream("GET", "https://aexit.example/s")
        async with stream_cm as resp:
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_relative_url_goes_local_without_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mock_httpx_client(monkeypatch, lambda r: httpx2.Response(200))
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        response = await client.request("GET", "/relative-only")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_absolute_request_url_requires_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mock_httpx_client(monkeypatch, lambda r: httpx2.Response(200))
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        with pytest.raises(ValueError, match="base_url"):
            client.absolute_request_url("/relative-only")


@pytest.mark.asyncio
@pytest.mark.timeout(10)
@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "localhost",
        "10.0.0.1",
        "192.168.1.1",
        "172.16.0.1",
        "app.localhost",
    ],
)
async def test_smart_local_skip_proxy_no_rotation(host: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # Предпочтение прокси уже стоит, прокси мёртвый. Локальный хост не заходит в ротацию,
    # поэтому ключ остаётся. Ротация при обрыве прокси ключ снимает.
    async with _serve_http("127.0.0.1", 200, b"ok") as port:
        url = f"http://{host}:{port}/r"
        _force_proxy(monkeypatch, "http://127.0.0.1:9")
        origin = normalized_http_origin(url)
        await egress_prefer_proxy_set(origin)
        try:
            async with get_httpx_client(timeout=0.4, strategy=ProxyStrategy.SMART) as client:
                if host in ("127.0.0.1", "localhost"):
                    response = await client.request("GET", url)
                    assert response.status_code == 200
                    await response.aclose()
                else:
                    try:
                        response = await client.request("GET", url)
                    except (httpx2.ConnectError, httpx2.ConnectTimeout):
                        response = None
                    else:
                        assert response.status_code == 200
                        await response.aclose()
            assert await egress_prefer_proxy_get(origin) is True
        finally:
            await egress_prefer_proxy_delete(origin)


@pytest.mark.asyncio
async def test_local_connect_error_retried_until_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Потерянный под нагрузкой SYN к loopback-listener'у переживается повтором:
    connect не дошёл до сервера — запрос не был отправлен."""
    calls = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx2.ConnectError("syn lost", request=request)
        return httpx2.Response(200)

    install_mock_httpx_client(monkeypatch, handler)
    monkeypatch.setattr(SmartProxyClient, "LOCAL_CONNECT_RETRY_DELAY_SEC", 0.0)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.DIRECT_FIRST) as client:
        response = await client.request("GET", "http://127.0.0.1:9025/x")
    assert response.status_code == 200
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_local_connect_error_exhausts_attempts_and_raises_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        raise httpx2.ConnectError("refused", request=request)

    install_mock_httpx_client(monkeypatch, handler)
    monkeypatch.setattr(SmartProxyClient, "LOCAL_CONNECT_RETRY_DELAY_SEC", 0.0)
    with pytest.raises(httpx2.ConnectError, match="refused"):
        async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.DIRECT_FIRST) as client:
            _ = await client.request("GET", "http://127.0.0.1:9025/x")
    assert calls["n"] == SmartProxyClient.LOCAL_CONNECT_ATTEMPTS


@pytest.mark.asyncio
async def test_local_stream_connect_error_retried_until_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FlakyStream:
        def __init__(self, fail: bool) -> None:
            self._fail: bool = fail

        async def __aenter__(self) -> httpx2.Response:
            if self._fail:
                raise httpx2.ConnectError(
                    "syn lost", request=httpx2.Request("GET", "http://127.0.0.1:9025/s")
                )
            return httpx2.Response(200)

        async def __aexit__(self, *args: object) -> None:
            return None

    calls = {"n": 0}

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def aclose(self) -> None:
            return None

        def stream(self, _method: str, _url: str, **_kwargs: object) -> FlakyStream:
            calls["n"] += 1
            return FlakyStream(fail=calls["n"] < 3)

    monkeypatch.setattr(httpx2, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(SmartProxyClient, "LOCAL_CONNECT_RETRY_DELAY_SEC", 0.0)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.DIRECT_FIRST) as client:
        async with client.stream("GET", "http://127.0.0.1:9025/s") as resp:
            assert resp.status_code == 200
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_smart_429_retries_via_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    first = ClosedCallResponse(429)

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._proxy_kw = kwargs.get("proxy")

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def request(self, method: str, url: str, **kwargs: object) -> object:
            if self._proxy_kw is None:
                return first
            return httpx2.Response(200)

    _proxy_settings(monkeypatch)
    monkeypatch.setattr("core.http.client.httpx2.AsyncClient", FakeAsyncClient)
    _enable_proxy(monkeypatch)
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        r = await client.request("GET", "https://retry-429.example/x")
    assert r.status_code == 200
    assert first.aclose_calls == 1
    assert await egress_prefer_proxy_get(normalized_http_origin("https://retry-429.example/x")) is True
    await egress_prefer_proxy_delete(normalized_http_origin("https://retry-429.example/x"))


@pytest.mark.asyncio
async def test_smart_451_retries_via_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    first = ClosedCallResponse(451)

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._proxy_kw = kwargs.get("proxy")

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def request(self, method: str, url: str, **kwargs: object) -> object:
            if self._proxy_kw is None:
                return first
            return httpx2.Response(200)

    _proxy_settings(monkeypatch)
    monkeypatch.setattr("core.http.client.httpx2.AsyncClient", FakeAsyncClient)
    _enable_proxy(monkeypatch)
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        r = await client.request("GET", "https://retry-451.example/x")
    assert r.status_code == 200
    assert first.aclose_calls == 1
    assert await egress_prefer_proxy_get(normalized_http_origin("https://retry-451.example/x")) is True
    await egress_prefer_proxy_delete(normalized_http_origin("https://retry-451.example/x"))


@pytest.mark.asyncio
async def test_smart_401_retries_when_setting_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _proxy_settings(monkeypatch)
    monkeypatch.setattr(
        "core.http.client._retry_http_statuses_for_smart",
        lambda: frozenset({401, 403, 429, 451}),
    )

    first = ClosedCallResponse(401)

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._proxy_kw = kwargs.get("proxy")

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def request(self, method: str, url: str, **kwargs: object) -> object:
            if self._proxy_kw is None:
                return first
            return httpx2.Response(200)

    monkeypatch.setattr("core.http.client.httpx2.AsyncClient", FakeAsyncClient)
    _enable_proxy(monkeypatch)
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        r = await client.request("GET", "https://retry-401.example/x")
    assert r.status_code == 200
    assert first.aclose_calls == 1
    assert await egress_prefer_proxy_get(normalized_http_origin("https://retry-401.example/x")) is True
    await egress_prefer_proxy_delete(normalized_http_origin("https://retry-401.example/x"))


@pytest.mark.asyncio
async def test_prefer_proxy_rotation_connect_error_invalidates(monkeypatch: pytest.MonkeyPatch) -> None:
    # 127.0.0.1.nip.io резолвится в loopback, но имя не входит в локальные хосты клиента.
    async with _serve_http("127.0.0.1", 200, b"ok") as port:
        url = f"http://127.0.0.1.nip.io:{port}/x"
        _force_proxy(monkeypatch, "http://127.0.0.1:9")
        origin = normalized_http_origin(url)
        await egress_prefer_proxy_set(origin)
        try:
            async with get_httpx_client(timeout=0.4, strategy=ProxyStrategy.SMART) as client:
                response = await client.request("GET", url)
            assert response.status_code == 200
            await response.aclose()
            assert await egress_prefer_proxy_get(origin) is False
        finally:
            await egress_prefer_proxy_delete(origin)


@pytest.mark.asyncio
async def test_prefer_proxy_error_status_falls_back_direct(monkeypatch: pytest.MonkeyPatch) -> None:
    async with _serve_http("127.0.0.1", 503, b"") as proxy_port:
        async with _serve_http("127.0.0.1", 200, b"ok") as port:
            url = f"http://127.0.0.1.nip.io:{port}/x"
            _force_proxy(monkeypatch, f"http://127.0.0.1:{proxy_port}")
            origin = normalized_http_origin(url)
            await egress_prefer_proxy_set(origin)
            try:
                async with get_httpx_client(timeout=0.4, strategy=ProxyStrategy.SMART) as client:
                    response = await client.request("GET", url)
                assert response.status_code == 200
                await response.aclose()
                assert await egress_prefer_proxy_get(origin) is False
            finally:
                await egress_prefer_proxy_delete(origin)


@pytest.mark.asyncio
async def test_stream_smart_mock_transport_200(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mock_httpx_client(monkeypatch, lambda r: httpx2.Response(200, content=b"ok"))
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        async with client.stream("GET", "https://stream.example/s") as resp:
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_stream_smart_connect_then_proxy_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class StreamFailDirect:
        async def __aenter__(self) -> object:
            raise httpx2.ConnectError("d", request=httpx2.Request("GET", "https://x"))

        async def __aexit__(self, *args: object) -> None:
            return None

    class StreamOk:
        async def __aenter__(self) -> httpx2.Response:
            return httpx2.Response(200, content=b"p")

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._proxy_kw = kwargs.get("proxy")

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def aclose(self) -> None:
            return None

        def stream(self, method: str, url: str, **kwargs: object) -> StreamFailDirect | StreamOk:
            if self._proxy_kw is None:
                return StreamFailDirect()
            return StreamOk()

    _proxy_settings(monkeypatch)
    monkeypatch.setattr("core.http.client.httpx2.AsyncClient", FakeAsyncClient)
    _enable_proxy(monkeypatch)
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        async with client.stream("GET", "https://stream-smart.example/s") as resp:
            assert resp.status_code == 200
    assert await egress_prefer_proxy_get(normalized_http_origin("https://stream-smart.example/s")) is True
    await egress_prefer_proxy_delete(normalized_http_origin("https://stream-smart.example/s"))


@pytest.mark.asyncio
async def test_smart_request_connect_fail_then_proxy_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._proxy_kw = kwargs.get("proxy")

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def aclose(self) -> None:
            return None

        async def request(self, http_method: str, url: str, **kwargs: object) -> httpx2.Response:
            if self._proxy_kw is None:
                raise httpx2.ConnectError("d", request=httpx2.Request(http_method, url))
            return httpx2.Response(200)

    _proxy_settings(monkeypatch)
    monkeypatch.setattr("core.http.client.httpx2.AsyncClient", FakeAsyncClient)
    _enable_proxy(monkeypatch)
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        r = await client.request("GET", "https://smart-req-fail-then-proxy.example/x")
    assert r.status_code == 200
    assert await egress_prefer_proxy_get(
        normalized_http_origin("https://smart-req-fail-then-proxy.example/x")
    ) is True
    await egress_prefer_proxy_delete(normalized_http_origin("https://smart-req-fail-then-proxy.example/x"))


@pytest.mark.asyncio
async def test_stream_direct_connect_fail_all_proxy_streams_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    class StreamFail:
        async def __aenter__(self) -> object:
            raise httpx2.ConnectError("f", request=httpx2.Request("GET", "https://x"))

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def aclose(self) -> None:
            return None

        def stream(self, method: str, url: str, **kwargs: object) -> StreamFail:
            return StreamFail()

    _proxy_settings(monkeypatch)
    monkeypatch.setattr("core.http.client.httpx2.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    with pytest.raises(httpx2.ConnectError):
        async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
            async with client.stream("GET", "https://stream-all-proxy-dead.example/s"):
                pass


@pytest.mark.asyncio
async def test_stream_smart_403_retries_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    class StreamCM403:
        async def __aenter__(self) -> httpx2.Response:
            return httpx2.Response(403)

        async def __aexit__(self, *args: object) -> None:
            return None

    class StreamCM200:
        async def __aenter__(self) -> httpx2.Response:
            return httpx2.Response(200)

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._proxy_kw = kwargs.get("proxy")

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def aclose(self) -> None:
            return None

        def stream(self, method: str, url: str, **kwargs: object) -> StreamCM403 | StreamCM200:
            if self._proxy_kw is None:
                return StreamCM403()
            return StreamCM200()

    _proxy_settings(monkeypatch)
    monkeypatch.setattr("core.http.client.httpx2.AsyncClient", FakeAsyncClient)
    _enable_proxy(monkeypatch)
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        async with client.stream("GET", "https://stream-403.example/s") as resp:
            assert resp.status_code == 200
    assert await egress_prefer_proxy_get(normalized_http_origin("https://stream-403.example/s")) is True
    await egress_prefer_proxy_delete(normalized_http_origin("https://stream-403.example/s"))


@pytest.mark.asyncio
async def test_stream_prefer_proxy_non_success_falls_back_direct(monkeypatch: pytest.MonkeyPatch) -> None:
    class Bad:
        async def __aenter__(self) -> object:
            r = MagicMock()
            r.status_code = 500
            type(r).is_success = PropertyMock(return_value=False)
            return r

        async def __aexit__(self, *args: object) -> None:
            return None

    class Ok:
        async def __aenter__(self) -> httpx2.Response:
            return httpx2.Response(200)

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._proxy_kw = kwargs.get("proxy")

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def aclose(self) -> None:
            return None

        def stream(self, method: str, url: str, **kwargs: object) -> Bad | Ok:
            if self._proxy_kw is not None:
                return Bad()
            return Ok()

    monkeypatch.setattr("core.http.client.httpx2.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    _proxy_settings(monkeypatch)
    async with _prefer_proxy_origin(monkeypatch, "https://stream-prefer-bad.example/s"):
        async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
            async with client.stream("GET", "https://stream-prefer-bad.example/s") as resp:
                assert resp.status_code == 200
        assert await egress_prefer_proxy_get(
            normalized_http_origin("https://stream-prefer-bad.example/s")
        ) is False


@pytest.mark.asyncio
async def test_stream_prefer_all_proxies_fail_then_direct(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingStream:
        async def __aenter__(self) -> object:
            raise httpx2.ConnectError("p", request=httpx2.Request("GET", "https://x"))

        async def __aexit__(self, *args: object) -> None:
            return None

    class OkStream:
        async def __aenter__(self) -> httpx2.Response:
            return httpx2.Response(200)

        async def __aexit__(self, *args: object) -> None:
            return None

    phase = {"n": 0}

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._proxy_kw = kwargs.get("proxy")

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def aclose(self) -> None:
            return None

        def stream(self, method: str, url: str, **kwargs: object) -> FailingStream | OkStream:
            if self._proxy_kw is not None:
                return FailingStream()
            phase["n"] += 1
            return OkStream()

    _proxy_settings(monkeypatch)
    monkeypatch.setattr("core.http.client.httpx2.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    async with _prefer_proxy_origin(monkeypatch, "https://stream-prefer-dead.example/s"):
        async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
            async with client.stream("GET", "https://stream-prefer-dead.example/s") as resp:
                assert resp.status_code == 200
        assert await egress_prefer_proxy_get(
            normalized_http_origin("https://stream-prefer-dead.example/s")
        ) is False


@pytest.mark.asyncio
async def test_request_public_oauth_direct_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mock_httpx_client(monkeypatch, lambda r: httpx2.Response(200, text="d"))
    r = await request_public_oauth("GET", "https://oauth.example/ok", timeout=5.0, httpx_client_kwargs={})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_request_public_oauth_proxy_after_direct_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    n = {"i": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        n["i"] += 1
        if n["i"] <= 3:
            raise httpx2.ConnectError("d", request=request)
        return httpx2.Response(200, text="via")

    install_mock_httpx_client(
        monkeypatch,
        cast(Callable[[httpx2.Request], httpx2.Response], handler),
    )
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    _proxy_settings(monkeypatch)
    r = await request_public_oauth("GET", "https://oauth.example/p", timeout=5.0, httpx_client_kwargs={})
    assert r.status_code == 200
    assert n["i"] == 4


@pytest.mark.asyncio
async def test_request_public_oauth_proxy_fail_then_direct_burst(monkeypatch: pytest.MonkeyPatch) -> None:
    n = {"i": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        n["i"] += 1
        if n["i"] <= 4:
            raise httpx2.ConnectError("x", request=request)
        return httpx2.Response(200, text="final")

    install_mock_httpx_client(
        monkeypatch,
        cast(Callable[[httpx2.Request], httpx2.Response], handler),
    )
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    _proxy_settings(monkeypatch)
    r = await request_public_oauth("GET", "https://oauth.example/both", timeout=5.0, httpx_client_kwargs={})
    assert r.status_code == 200
    assert n["i"] == 5


@pytest.mark.asyncio
async def test_is_local_url_unparsable_uses_false(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str) -> object:
        raise RuntimeError("parse")

    monkeypatch.setattr("core.http.client.urlparse", boom)
    c = SmartProxyClient(timeout=5.0, use_proxy=False)
    assert c.is_local_url("http://example.com") is False


@pytest.mark.asyncio
async def test_stream_proxy_only_rotates(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailTwiceThenOk:
        def __init__(self) -> None:
            self.calls = 0

        def stream(self, method: str, url: str, **kwargs: object) -> StreamContext:
            self.calls += 1
            return StreamContext(self.calls)

    class StreamContext:
        def __init__(self, n: int) -> None:
            self._n = n

        async def __aenter__(self) -> httpx2.Response:
            if self._n < 3:
                raise httpx2.ConnectError("p", request=httpx2.Request("GET", "https://x"))
            return httpx2.Response(200)

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            outer_raw = kwargs.pop("_outer")
            if not isinstance(outer_raw, FailTwiceThenOk):
                raise TypeError("_outer must be FailTwiceThenOk")
            self._outer = outer_raw

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def aclose(self) -> None:
            return None

        def stream(self, method: str, url: str, **kwargs: object) -> StreamContext:
            return self._outer.stream(method, url, **kwargs)

    outer = FailTwiceThenOk()

    def factory(*args: object, **kwargs: object) -> FakeAsyncClient:
        kwargs.setdefault("_outer", outer)
        return FakeAsyncClient(*args, **kwargs)

    _proxy_settings(monkeypatch)
    monkeypatch.setattr("core.http.client.httpx2.AsyncClient", factory)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.PROXY_ONLY) as client:
        async with client.stream("GET", "https://p-only.example/s") as resp:
            assert resp.status_code == 200
    assert outer.calls == 3


@pytest.mark.asyncio
async def test_stream_plain_400_does_not_raise_response_not_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SMART stream: обычный 400 с непрочитанным телом не падает ResponseNotRead и не уходит в proxy."""
    error_body = b'{"error":{"message":"The model nvidia/NVIDIA-Nemotron is not supported"}}'
    calls = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        return unread_json_response(request, 400, error_body)

    install_mock_httpx_client(monkeypatch, handler)
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    _proxy_settings(monkeypatch)

    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        async with client.stream("POST", "https://router.huggingface.co/v1/chat/completions") as resp:
            assert resp.status_code == 400
            assert "NVIDIA-Nemotron" in resp.text

    assert calls["n"] == 1
