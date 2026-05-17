"""Интеграционные тесты SmartProxyClient/stream/oauth с MockTransport и точечными monkeypatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import httpx
import pytest

from core.http.client import (
    ProxyStrategy,
    SmartProxyClient,
    _request_direct_burst,
    _retry_http_statuses_for_smart,
    get_httpx_client,
    request_public_oauth,
)
from tests.core.http_proxy_helpers import install_mock_httpx_client


def _proxy_settings(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock_settings = MagicMock()
    mock_settings.proxy.get_next_proxy.return_value = "http://127.0.0.1:9"
    mock_settings.proxy.connect_timeout = 15.0
    mock_settings.proxy.mark_last_proxy_failed = MagicMock()
    monkeypatch.setattr("core.http.client.SmartProxyClient._get_settings", lambda self: mock_settings)
    return mock_settings


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
    def handler(request: httpx.Request) -> None:
        raise httpx.ConnectError("burst", request=request)

    install_mock_httpx_client(monkeypatch, handler)
    with pytest.raises(httpx.ConnectError, match="burst"):
        await _request_direct_burst("GET", "https://burst.example/x", timeout=1.0, attempts=2)


@pytest.mark.asyncio
async def test_request_direct_burst_zero_attempts_raises() -> None:
    with pytest.raises(RuntimeError, match="attempts must be"):
        await _request_direct_burst("GET", "https://x.test/z", timeout=1.0, attempts=0)


@pytest.mark.asyncio
async def test_relative_path_resolves_with_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mock_httpx_client(monkeypatch, lambda r: httpx.Response(200))
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=False))
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART, base_url="https://api.example") as client:
        r = await client.request("GET", "/v1/r")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_smart_connect_failure_raises_when_proxy_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> None:
        raise httpx.ConnectError("x", request=request)

    install_mock_httpx_client(monkeypatch, handler)
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=False))
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: False)
    with pytest.raises(httpx.ConnectError):
        async with get_httpx_client(strategy=ProxyStrategy.SMART) as client:
            await client.request("GET", "https://no-proxy-fail.example/y")


@pytest.mark.asyncio
async def test_stream_smart_connect_failure_raises_when_proxy_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StreamFail:
        async def __aenter__(self) -> object:
            raise httpx.ConnectError("s", request=httpx.Request("GET", "https://x"))

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

    monkeypatch.setattr("core.http.client.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=False))
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: False)
    with pytest.raises(httpx.ConnectError):
        async with get_httpx_client(strategy=ProxyStrategy.SMART) as client:
            async with client.stream("GET", "https://stream-no-proxy.example/s"):
                pass


@pytest.mark.asyncio
async def test_stream_direct_first_local(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mock_httpx_client(monkeypatch, lambda r: httpx.Response(201))
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=False))
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.DIRECT_FIRST) as client:
        async with client.stream("GET", "http://127.0.0.1:8010/df") as resp:
            assert resp.status_code == 201


@pytest.mark.asyncio
async def test_stream_direct_first_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mock_httpx_client(monkeypatch, lambda r: httpx.Response(200))
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=False))
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.DIRECT_FIRST) as client:
        async with client.stream("GET", "https://df-remote.example/s") as resp:
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_http_method_shortcuts(monkeypatch: pytest.MonkeyPatch) -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(200)

    install_mock_httpx_client(monkeypatch, handler)
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=False))
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        await client.get("https://m.example/g")
        await client.post("https://m.example/p")
        await client.put("https://m.example/u")
        await client.delete("https://m.example/d")
        await client.patch("https://m.example/a")
    assert methods == ["GET", "POST", "PUT", "DELETE", "PATCH"]


@pytest.mark.asyncio
async def test_smart_proxy_client_aclose_inner_client() -> None:
    inner = MagicMock()
    inner.aclose = AsyncMock()
    client = get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART)
    client._client = inner
    await client.aclose()
    inner.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_smart_proxy_client_aexit_closes_inner_client() -> None:
    inner = MagicMock()
    inner.aclose = AsyncMock()
    client = get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART)
    client._client = inner
    async with client:
        pass
    inner.aclose.assert_awaited_once()


def test_get_settings_cached_on_smart_client() -> None:
    client = SmartProxyClient(timeout=5.0, use_proxy=False)
    first = client._get_settings()
    second = client._get_settings()
    assert first is second


@pytest.mark.asyncio
async def test_stream_prefer_sticky_success_calls_set(monkeypatch: pytest.MonkeyPatch) -> None:
    class StreamOk:
        async def __aenter__(self) -> httpx.Response:
            return httpx.Response(200)

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

    mock_set = AsyncMock()
    monkeypatch.setattr("core.http.client.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=True))
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_set", mock_set)
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    _proxy_settings(monkeypatch)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        async with client.stream("GET", "https://sticky-ok.example/s") as resp:
            assert resp.status_code == 200
    mock_set.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_prefer_zero_retries_raises_unexpected_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(SmartProxyClient, "MAX_PROXY_RETRIES", 0)
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=True))
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    _proxy_settings(monkeypatch)
    with pytest.raises(RuntimeError, match="unexpected state"):
        async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
            async with client.stream("GET", "https://sticky-zero.example/s"):
                pass


@pytest.mark.asyncio
async def test_stream_403_proxy_phase_all_connect_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    class Direct403:
        async def __aenter__(self) -> httpx.Response:
            return httpx.Response(403)

        async def __aexit__(self, *args: object) -> None:
            return None

    class ProxyFail:
        async def __aenter__(self) -> object:
            raise httpx.ConnectError("px", request=httpx.Request("GET", "https://x"))

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
    monkeypatch.setattr("core.http.client.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=False))
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    with pytest.raises(httpx.ConnectError):
        async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
            async with client.stream("GET", "https://stream-403-dead.example/s"):
                pass


@pytest.mark.asyncio
async def test_stream_proxy_only_all_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    class AlwaysFail:
        async def __aenter__(self) -> object:
            raise httpx.ConnectError("p", request=httpx.Request("GET", "https://x"))

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
    monkeypatch.setattr("core.http.client.httpx.AsyncClient", FakeAsyncClient)
    with pytest.raises(httpx.ConnectError):
        async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.PROXY_ONLY) as client:
            async with client.stream("GET", "https://p-only-dead.example/s"):
                pass


@pytest.mark.asyncio
async def test_stream_context_aexit_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mock_httpx_client(monkeypatch, lambda r: httpx.Response(200))
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=False))
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        stream_cm = client.stream("GET", "https://aexit.example/s")
        async with stream_cm as resp:
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_relative_url_requires_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mock_httpx_client(monkeypatch, lambda r: httpx.Response(200))
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=False))
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        with pytest.raises(ValueError, match="base_url"):
            await client.request("GET", "/relative-only")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host_url",
    [
        "http://127.0.0.1:8010/r",
        "http://localhost:8010/r",
        "http://10.0.0.1:8010/r",
        "http://192.168.1.1:8010/r",
        "http://172.16.0.1:8010/r",
        "http://app.localhost:8010/r",
    ],
)
async def test_smart_local_skip_proxy_no_rotation(host_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    via = AsyncMock()
    install_mock_httpx_client(monkeypatch, lambda r: httpx.Response(200))
    monkeypatch.setattr("core.http.client.SmartProxyClient._request_via_proxy_rotation", via)
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=False))
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        r = await client.request("GET", host_url)
    assert r.status_code == 200
    via.assert_not_called()


@pytest.mark.asyncio
async def test_smart_429_retries_via_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    first = MagicMock()
    first.status_code = 429
    first.aclose = AsyncMock()

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
            return httpx.Response(200)

    _proxy_settings(monkeypatch)
    monkeypatch.setattr("core.http.client.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=False))
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_set", AsyncMock())
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        r = await client.request("GET", "https://retry-429.example/x")
    assert r.status_code == 200
    first.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_smart_451_retries_via_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    first = MagicMock()
    first.status_code = 451
    first.aclose = AsyncMock()

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
            return httpx.Response(200)

    _proxy_settings(monkeypatch)
    monkeypatch.setattr("core.http.client.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=False))
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_set", AsyncMock())
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        r = await client.request("GET", "https://retry-451.example/x")
    assert r.status_code == 200
    first.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_smart_401_retries_when_setting_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _proxy_settings(monkeypatch)
    monkeypatch.setattr(
        "core.http.client._retry_http_statuses_for_smart",
        lambda: frozenset({401, 403, 429, 451}),
    )

    first = MagicMock()
    first.status_code = 401
    first.aclose = AsyncMock()

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
            return httpx.Response(200)

    monkeypatch.setattr("core.http.client.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=False))
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_set", AsyncMock())
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        r = await client.request("GET", "https://retry-401.example/x")
    assert r.status_code == 200
    first.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_prefer_proxy_rotation_connect_error_invalidates(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mock_httpx_client(monkeypatch, lambda r: httpx.Response(200))
    mock_del = AsyncMock()
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=True))
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_delete", mock_del)
    monkeypatch.setattr(
        "core.http.client.SmartProxyClient._request_via_proxy_rotation",
        AsyncMock(side_effect=httpx.ConnectError("rot", request=httpx.Request("GET", "https://x"))),
    )
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        r = await client.request("GET", "https://prefer-fail.example/x")
    assert r.status_code == 200
    mock_del.assert_awaited()


@pytest.mark.asyncio
async def test_prefer_proxy_error_status_falls_back_direct(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = MagicMock()
    bad.status_code = 503
    type(bad).is_success = PropertyMock(return_value=False)
    bad.aclose = AsyncMock()

    install_mock_httpx_client(monkeypatch, lambda r: httpx.Response(200))
    mock_del = AsyncMock()
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=True))
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_delete", mock_del)
    monkeypatch.setattr("core.http.client.SmartProxyClient._request_via_proxy_rotation", AsyncMock(return_value=bad))
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        r = await client.request("GET", "https://prefer-503.example/x")
    assert r.status_code == 200
    bad.aclose.assert_awaited_once()
    mock_del.assert_awaited()


@pytest.mark.asyncio
async def test_stream_smart_mock_transport_200(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mock_httpx_client(monkeypatch, lambda r: httpx.Response(200, content=b"ok"))
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=False))
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        async with client.stream("GET", "https://stream.example/s") as resp:
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_stream_smart_connect_then_proxy_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class StreamFailDirect:
        async def __aenter__(self) -> object:
            raise httpx.ConnectError("d", request=httpx.Request("GET", "https://x"))

        async def __aexit__(self, *args: object) -> None:
            return None

    class StreamOk:
        async def __aenter__(self) -> httpx.Response:
            return httpx.Response(200, content=b"p")

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
    monkeypatch.setattr("core.http.client.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=False))
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_set", AsyncMock())
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        async with client.stream("GET", "https://stream-smart.example/s") as resp:
            assert resp.status_code == 200


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

        async def request(self, http_method: str, url: str, **kwargs: object) -> httpx.Response:
            if self._proxy_kw is None:
                raise httpx.ConnectError("d", request=httpx.Request(http_method, url))
            return httpx.Response(200)

    _proxy_settings(monkeypatch)
    monkeypatch.setattr("core.http.client.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=False))
    mock_set = AsyncMock()
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_set", mock_set)
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        r = await client.request("GET", "https://smart-req-fail-then-proxy.example/x")
    assert r.status_code == 200
    mock_set.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_direct_connect_fail_all_proxy_streams_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    class StreamFail:
        async def __aenter__(self) -> object:
            raise httpx.ConnectError("f", request=httpx.Request("GET", "https://x"))

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
    monkeypatch.setattr("core.http.client.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=False))
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    with pytest.raises(httpx.ConnectError):
        async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
            async with client.stream("GET", "https://stream-all-proxy-dead.example/s"):
                pass


@pytest.mark.asyncio
async def test_stream_smart_403_retries_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    class StreamCM403:
        async def __aenter__(self) -> httpx.Response:
            return httpx.Response(403)

        async def __aexit__(self, *args: object) -> None:
            return None

    class StreamCM200:
        async def __aenter__(self) -> httpx.Response:
            return httpx.Response(200)

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
    monkeypatch.setattr("core.http.client.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=False))
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_set", AsyncMock())
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        async with client.stream("GET", "https://stream-403.example/s") as resp:
            assert resp.status_code == 200


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
        async def __aenter__(self) -> httpx.Response:
            return httpx.Response(200)

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

    monkeypatch.setattr("core.http.client.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=True))
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_delete", AsyncMock())
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    _proxy_settings(monkeypatch)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        async with client.stream("GET", "https://stream-prefer-bad.example/s") as resp:
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_stream_prefer_all_proxies_fail_then_direct(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingStream:
        async def __aenter__(self) -> object:
            raise httpx.ConnectError("p", request=httpx.Request("GET", "https://x"))

        async def __aexit__(self, *args: object) -> None:
            return None

    class OkStream:
        async def __aenter__(self) -> httpx.Response:
            return httpx.Response(200)

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
    monkeypatch.setattr("core.http.client.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_get", AsyncMock(return_value=True))
    monkeypatch.setattr("core.http.client.egress_prefer_proxy_delete", AsyncMock())
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.SMART) as client:
        async with client.stream("GET", "https://stream-prefer-dead.example/s") as resp:
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_request_public_oauth_direct_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mock_httpx_client(monkeypatch, lambda r: httpx.Response(200, text="d"))
    r = await request_public_oauth("GET", "https://oauth.example/ok", timeout=5.0, httpx_client_kwargs={})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_request_public_oauth_proxy_after_direct_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    n = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        n["i"] += 1
        if n["i"] <= 3:
            raise httpx.ConnectError("d", request=request)
        return httpx.Response(200, text="via")

    install_mock_httpx_client(monkeypatch, handler)
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)
    _proxy_settings(monkeypatch)
    r = await request_public_oauth("GET", "https://oauth.example/p", timeout=5.0, httpx_client_kwargs={})
    assert r.status_code == 200
    assert n["i"] == 4


@pytest.mark.asyncio
async def test_request_public_oauth_proxy_fail_then_direct_burst(monkeypatch: pytest.MonkeyPatch) -> None:
    n = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        n["i"] += 1
        if n["i"] <= 4:
            raise httpx.ConnectError("x", request=request)
        return httpx.Response(200, text="final")

    install_mock_httpx_client(monkeypatch, handler)
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
    assert c._is_local_url("http://example.com") is False


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

        async def __aenter__(self) -> httpx.Response:
            if self._n < 3:
                raise httpx.ConnectError("p", request=httpx.Request("GET", "https://x"))
            return httpx.Response(200)

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._outer: FailTwiceThenOk = kwargs.pop("_outer")

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
    monkeypatch.setattr("core.http.client.httpx.AsyncClient", factory)
    async with get_httpx_client(timeout=5.0, strategy=ProxyStrategy.PROXY_ONLY) as client:
        async with client.stream("GET", "https://p-only.example/s") as resp:
            assert resp.status_code == 200
    assert outer.calls == 3
