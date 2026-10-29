"""Тесты для программируемой стратегии прокси в HTTP клиенте."""

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import httpx2
import pytest

from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.http.client import ProxyStrategy, get_httpx_client, request_with_strategy
from core.http.egress_route_preference import (
    egress_prefer_proxy_delete,
    egress_prefer_proxy_get,
    egress_prefer_proxy_set,
    normalized_http_origin,
    redis_key_for_origin,
)
from tests.core.http_proxy_helpers import ClosedCallResponse

# Имя резолвится в 127.0.0.1, но не входит в локальные хосты клиента, поэтому запрос идёт в прокси.
_NON_LOCAL_HOST = "127.0.0.1.nip.io"


def _force_proxy(
    monkeypatch: pytest.MonkeyPatch,
    proxy_url: str,
    *,
    connect_timeout: float = 0.4,
) -> None:
    proxy = get_settings().proxy
    monkeypatch.setattr(proxy, "enabled", True)
    monkeypatch.setattr(proxy, "proxies", [proxy_url])
    monkeypatch.setattr(proxy, "connect_timeout", connect_timeout)


@asynccontextmanager
async def _serve_http(
    status_code: int,
    body: bytes,
    *,
    captured: list[bytes] | None = None,
    host: str = "127.0.0.1",
    port: int = 0,
) -> AsyncIterator[int]:
    reason = "OK" if status_code == 200 else "Error"

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        headers = b""
        while True:
            line = await reader.readline()
            headers += line
            if line in (b"\r\n", b""):
                break
        length = 0
        for header in headers.split(b"\r\n"):
            if header.lower().startswith(b"content-length:"):
                length = int(header.split(b":", 1)[1].strip())
        payload = await reader.readexactly(length) if length else b""
        if captured is not None:
            captured.append(payload)
        head = (
            f"HTTP/1.1 {status_code} {reason}\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode()
        writer.write(head + body)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle, host, port)
    sockets = server.sockets
    if sockets is None or len(sockets) == 0:
        server.close()
        await server.wait_closed()
        raise RuntimeError("http test listener has no socket")
    bound_port = int(sockets[0].getsockname()[1])
    try:
        yield bound_port
    finally:
        server.close()
        await server.wait_closed()


async def _ephemeral_port() -> int:
    async with _serve_http(200, b"") as port:
        return port


async def _origin_ok(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while True:
        line = await reader.readline()
        if line in (b"\r\n", b""):
            break
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
    await writer.drain()
    writer.close()
    await writer.wait_closed()


class TestProxyStrategy:
    """Тесты стратегии прокси."""

    @pytest.mark.asyncio
    async def test_direct_only_success(self):
        """Тест DIRECT_ONLY - успешный прямой запрос."""
        with patch("core.http.client._request_direct_burst") as mock_direct:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_direct.return_value = mock_response

            response = await request_with_strategy(
                "GET",
                "https://example.com",
                strategy=ProxyStrategy.DIRECT_ONLY,
                direct_attempts=2,
                timeout=10.0,
            )

            assert response.status_code == 200
            mock_direct.assert_called_once()
            call_kwargs = mock_direct.call_args[1]
            assert call_kwargs["attempts"] == 2

    @pytest.mark.asyncio
    async def test_direct_only_failure(self):
        """Тест DIRECT_ONLY - прямой запрос не удался."""
        import httpx2

        with patch("core.http.client._request_direct_burst") as mock_direct:
            mock_direct.side_effect = httpx2.ConnectError("Connection failed")

            with pytest.raises(httpx2.ConnectError):
                await request_with_strategy(
                    "GET",
                    "https://example.com",
                    strategy=ProxyStrategy.DIRECT_ONLY,
                    direct_attempts=2,
                    timeout=10.0,
                )

            mock_direct.assert_called_once()

    @pytest.mark.asyncio
    async def test_proxy_only_with_active_proxy(self, monkeypatch: pytest.MonkeyPatch):
        """Тест PROXY_ONLY - прокси активен."""
        async with _serve_http(200, b"via-proxy") as proxy_port:
            _force_proxy(monkeypatch, f"http://127.0.0.1:{proxy_port}")
            response = await request_with_strategy(
                "GET",
                f"http://{_NON_LOCAL_HOST}:1/x",
                strategy=ProxyStrategy.PROXY_ONLY,
                proxy_attempts=3,
                timeout=1.0,
            )
            assert response.status_code == 200
            await response.aclose()

    @pytest.mark.asyncio
    async def test_proxy_only_without_proxy_configured(self):
        """Тест PROXY_ONLY - прокси не настроен."""
        import httpx2

        with patch("core.http.client._platform_proxy_active", return_value=False):
            with pytest.raises(httpx2.ConnectError, match="Proxy requested but not configured"):
                await request_with_strategy(
                    "GET",
                    "https://example.com",
                    strategy=ProxyStrategy.PROXY_ONLY,
                    timeout=10.0,
                )

    @pytest.mark.asyncio
    async def test_direct_first_success_on_direct(self):
        """Тест DIRECT_FIRST - успешный прямой запрос."""
        with patch("core.http.client.egress_prefer_proxy_get", new_callable=AsyncMock, return_value=False):
            with patch("core.http.client._request_direct_burst") as mock_direct:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_direct.return_value = mock_response

                response = await request_with_strategy(
                    "GET",
                    "https://example.com",
                    strategy=ProxyStrategy.DIRECT_FIRST,
                    direct_attempts=3,
                    proxy_attempts=3,
                    timeout=10.0,
                )

                assert response.status_code == 200
                mock_direct.assert_called_once()
                call_kwargs = mock_direct.call_args[1]
                assert call_kwargs["attempts"] == 3

    @pytest.mark.asyncio
    async def test_direct_first_fallback_to_proxy(self, monkeypatch: pytest.MonkeyPatch):
        """Тест DIRECT_FIRST - прямой запрос не удался, fallback на прокси."""
        url = f"http://{_NON_LOCAL_HOST}:1/x"
        origin = normalized_http_origin(url)
        async with _serve_http(200, b"via-proxy") as proxy_port:
            _force_proxy(monkeypatch, f"http://127.0.0.1:{proxy_port}")
            try:
                response = await request_with_strategy(
                    "GET",
                    url,
                    strategy=ProxyStrategy.DIRECT_FIRST,
                    direct_attempts=1,
                    proxy_attempts=1,
                    timeout=1.0,
                )
                assert response.status_code == 200
                await response.aclose()
                assert await egress_prefer_proxy_get(origin) is True
            finally:
                await egress_prefer_proxy_delete(origin)

    @pytest.mark.asyncio
    async def test_direct_first_fallback_json_not_passed_to_httpx_client_ctor(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """POST json к Telegram: fallback на прокси не должен пробрасывать json в AsyncClient."""
        url = f"http://{_NON_LOCAL_HOST}:1/sendMessage"
        origin = normalized_http_origin(url)
        captured: list[bytes] = []
        async with _serve_http(200, b"ok", captured=captured) as proxy_port:
            _force_proxy(monkeypatch, f"http://127.0.0.1:{proxy_port}")
            try:
                response = await request_with_strategy(
                    "POST",
                    url,
                    strategy=ProxyStrategy.DIRECT_FIRST,
                    direct_attempts=1,
                    proxy_attempts=1,
                    timeout=1.0,
                    json={"chat_id": "-1", "text": "x"},
                )
                assert response.status_code == 200
                await response.aclose()
                assert captured == [b'{"chat_id":"-1","text":"x"}']
            finally:
                await egress_prefer_proxy_delete(origin)

    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_direct_first_fallback_to_direct_after_proxy(self, monkeypatch: pytest.MonkeyPatch):
        """Тест DIRECT_FIRST - прямой и прокси не удались, повторное прямое."""
        port = await _ephemeral_port()
        url = f"http://{_NON_LOCAL_HOST}:{port}/x"
        origin = normalized_http_origin(url)

        async def open_origin() -> asyncio.Server:
            await asyncio.sleep(0.6)
            return await asyncio.start_server(_origin_ok, "127.0.0.1", port)

        _force_proxy(monkeypatch, "http://203.0.113.1:81", connect_timeout=0.4)
        opener = asyncio.create_task(open_origin())
        started = time.monotonic()
        try:
            response = await request_with_strategy(
                "GET",
                url,
                strategy=ProxyStrategy.DIRECT_FIRST,
                direct_attempts=1,
                proxy_attempts=1,
                timeout=1.0,
            )
            assert response.status_code == 200
            await response.aclose()
            assert time.monotonic() - started > 1.0
        finally:
            server = await opener
            server.close()
            await server.wait_closed()
            await egress_prefer_proxy_delete(origin)

    @pytest.mark.asyncio
    async def test_proxy_first_success_on_proxy(self, monkeypatch: pytest.MonkeyPatch):
        """Тест PROXY_FIRST - успешный запрос через прокси."""
        async with _serve_http(200, b"via-proxy") as proxy_port:
            _force_proxy(monkeypatch, f"http://127.0.0.1:{proxy_port}")
            response = await request_with_strategy(
                "GET",
                f"http://{_NON_LOCAL_HOST}:1/x",
                strategy=ProxyStrategy.PROXY_FIRST,
                proxy_attempts=1,
                direct_attempts=1,
                timeout=1.0,
            )
            assert response.status_code == 200
            await response.aclose()

    @pytest.mark.asyncio
    async def test_proxy_first_fallback_to_direct(self, monkeypatch: pytest.MonkeyPatch):
        """Тест PROXY_FIRST - прокси не удался, fallback на прямое."""
        async with _serve_http(200, b"direct") as port:
            _force_proxy(monkeypatch, "http://127.0.0.1:9")
            response = await request_with_strategy(
                "GET",
                f"http://{_NON_LOCAL_HOST}:{port}/x",
                strategy=ProxyStrategy.PROXY_FIRST,
                proxy_attempts=1,
                direct_attempts=1,
                timeout=1.0,
            )
            assert response.status_code == 200
            assert response.text == "direct"
            await response.aclose()

    @pytest.mark.asyncio
    async def test_proxy_first_without_proxy_configured(self):
        """Тест PROXY_FIRST - прокси не настроен, сразу прямое."""
        with patch("core.http.client._platform_proxy_active", return_value=False):
            with patch("core.http.client._request_direct_burst") as mock_direct:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_direct.return_value = mock_response

                response = await request_with_strategy(
                    "GET",
                    "https://example.com",
                    strategy=ProxyStrategy.PROXY_FIRST,
                    proxy_attempts=3,
                    direct_attempts=2,
                    timeout=10.0,
                )

                assert response.status_code == 200
                mock_direct.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_httpx_client_rejects_proxy_kwarg(self):
        with pytest.raises(ValueError, match="unsupported keyword 'proxy'"):
            get_httpx_client(proxy=True)  # pyright: ignore[reportCallIssue]

    @pytest.mark.asyncio
    async def test_smart_direct_200_no_proxy_rotation(self):
        """SMART: при 200 сразу возвращаем ответ, без второй фазы."""
        with patch("core.http.client.SmartProxyClient._request_via_proxy_rotation") as mock_proxy_path:
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            class FakeAsyncClient:
                def __init__(self, *args, **kwargs):
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    return None

                async def request(self, method, url, **kwargs):
                    return mock_resp

            with patch("core.http.client.httpx2.AsyncClient", FakeAsyncClient):
                with patch("core.http.client.egress_prefer_proxy_get", new_callable=AsyncMock, return_value=False):
                    with patch("core.http.client.egress_prefer_proxy_set", new_callable=AsyncMock):
                        async with get_httpx_client(timeout=10.0, strategy=ProxyStrategy.SMART) as client:
                            r = await client.request("GET", "https://api.example.com/x")

            assert r.status_code == 200
            mock_proxy_path.assert_not_called()

    @pytest.mark.asyncio
    async def test_smart_sticky_redis_prefers_proxy_first(self):
        """SMART: Redis говорит prefer proxy — сначала ротация прокси, без прямого запроса."""
        via_proxy = MagicMock()
        via_proxy.status_code = 200
        type(via_proxy).is_success = PropertyMock(return_value=True)

        with patch("core.http.client.egress_prefer_proxy_get", new_callable=AsyncMock, return_value=True):
            with patch("core.http.client.egress_prefer_proxy_set", new_callable=AsyncMock) as mock_set:
                with patch(
                    "core.http.client.SmartProxyClient._request_via_proxy_rotation",
                    new_callable=AsyncMock,
                    return_value=via_proxy,
                ) as mock_rotate:
                    with patch("core.http.client._platform_proxy_active", return_value=True):
                        async with get_httpx_client(timeout=10.0, strategy=ProxyStrategy.SMART) as client:
                            r = await client.request("GET", "https://api.example.com/x")

        assert r.status_code == 200
        mock_rotate.assert_awaited_once()
        mock_set.assert_awaited()

    @pytest.mark.asyncio
    async def test_egress_prefer_proxy_set_requires_ttl(self, monkeypatch: pytest.MonkeyPatch):
        """egress_prefer_proxy_set передаёт TTL в RedisClient.set."""
        origin = "https://ttl-check.example:443"
        proxy = get_settings().proxy
        monkeypatch.setattr(proxy, "enabled", True)
        monkeypatch.setattr(proxy, "proxies", ["http://127.0.0.1:9"])
        monkeypatch.setattr(proxy, "prefer_proxy_ttl_seconds", 120)
        try:
            await egress_prefer_proxy_set(origin)
            ttl = await RedisClient(get_settings().database.redis_url).ttl(redis_key_for_origin(origin))
            assert 60 < ttl <= 120
        finally:
            await egress_prefer_proxy_delete(origin)

    @pytest.mark.asyncio
    async def test_smart_403_retries_via_proxy_when_configured(self):
        """SMART: 403 напрямую, затем успех через platform proxy."""
        first = ClosedCallResponse(403)
        second = httpx2.Response(200)

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                self.proxy_kw = kwargs.get("proxy")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def request(self, method, url, **kwargs):
                if self.proxy_kw is None:
                    return first
                return second

        mock_settings = MagicMock()
        mock_settings.proxy.get_next_proxy.return_value = "http://127.0.0.1:1"
        mock_settings.proxy.connect_timeout = 15.0
        mock_settings.proxy.mark_last_proxy_failed = MagicMock()

        with patch("core.http.client.egress_prefer_proxy_get", new_callable=AsyncMock, return_value=False):
            with patch("core.http.client.egress_prefer_proxy_set", new_callable=AsyncMock):
                with patch("core.http.client.httpx2.AsyncClient", FakeAsyncClient):
                    with patch("core.http.client._platform_proxy_active", return_value=True):
                        with patch(
                            "core.http.client.SmartProxyClient._get_settings",
                            return_value=mock_settings,
                        ):
                            async with get_httpx_client(timeout=10.0, strategy=ProxyStrategy.SMART) as client:
                                r = await client.request("GET", "https://api.example.com/x")

        assert r.status_code == 200
        assert first.aclose_calls == 1

    @pytest.mark.asyncio
    async def test_smart_geo_400_retries_via_proxy_when_configured(self):
        """SMART: Google geo 400 напрямую, затем успех через platform proxy."""
        first = ClosedCallResponse(
            400,
            text=(
                '{"error":{"code":400,"message":"User location is not supported for the API use.",'
                '"status":"FAILED_PRECONDITION"}}'
            ),
        )
        second = httpx2.Response(200)

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                self.proxy_kw = kwargs.get("proxy")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def request(self, method, url, **kwargs):
                if self.proxy_kw is None:
                    return first
                return second

        mock_settings = MagicMock()
        mock_settings.proxy.get_next_proxy.return_value = "http://127.0.0.1:1"
        mock_settings.proxy.connect_timeout = 15.0
        mock_settings.proxy.mark_last_proxy_failed = MagicMock()

        with patch("core.http.client.egress_prefer_proxy_get", new_callable=AsyncMock, return_value=False):
            with patch("core.http.client.egress_prefer_proxy_set", new_callable=AsyncMock):
                with patch("core.http.client.httpx2.AsyncClient", FakeAsyncClient):
                    with patch("core.http.client._platform_proxy_active", return_value=True):
                        with patch(
                            "core.http.client.SmartProxyClient._get_settings",
                            return_value=mock_settings,
                        ):
                            async with get_httpx_client(timeout=10.0, strategy=ProxyStrategy.SMART) as client:
                                r = await client.request(
                                    "GET",
                                    "https://generativelanguage.googleapis.com/v1beta/openai/models",
                                )

        assert r.status_code == 200
        assert first.aclose_calls == 1

    @pytest.mark.asyncio
    async def test_smart_plain_400_does_not_retry_via_proxy(self):
        """SMART: обычный 400 без geo-маркеров не уходит в proxy."""
        first = ClosedCallResponse(400, text='{"error":{"message":"bad request"}}')

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                self.proxy_kw = kwargs.get("proxy")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def request(self, method, url, **kwargs):
                return first

        with patch("core.http.client.egress_prefer_proxy_get", new_callable=AsyncMock, return_value=False):
            with patch(
                "core.http.client.SmartProxyClient._request_via_proxy_rotation",
                new_callable=AsyncMock,
            ) as mock_rotate:
                with patch("core.http.client.httpx2.AsyncClient", FakeAsyncClient):
                    with patch("core.http.client._platform_proxy_active", return_value=True):
                        async with get_httpx_client(timeout=10.0, strategy=ProxyStrategy.SMART) as client:
                            r = await client.request("GET", "https://api.example.com/x")

        assert r.status_code == 400
        mock_rotate.assert_not_called()
        assert first.aclose_calls == 0

    @pytest.mark.asyncio
    async def test_smart_403_no_proxy_when_not_configured(self):
        """SMART: 403 и прокси выключен — отдаём первый ответ."""
        first = ClosedCallResponse(403)

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def request(self, method, url, **kwargs):
                return first

        with patch("core.http.client.httpx2.AsyncClient", FakeAsyncClient):
            with patch("core.http.client._platform_proxy_active", return_value=False):
                async with get_httpx_client(timeout=10.0, strategy=ProxyStrategy.SMART) as client:
                    r = await client.request("GET", "https://api.example.com/x")

        assert r.status_code == 403
        assert first.aclose_calls == 0

    @pytest.mark.asyncio
    async def test_request_with_strategy_smart_delegates(self, monkeypatch: pytest.MonkeyPatch):
        """request_with_strategy(SMART) при 403 повторяет запрос через platform proxy."""
        async with _serve_http(403, b"blocked") as origin_port:
            url = f"http://{_NON_LOCAL_HOST}:{origin_port}/x"
            origin = normalized_http_origin(url)
            async with _serve_http(200, b"via-proxy") as proxy_port:
                _force_proxy(monkeypatch, f"http://127.0.0.1:{proxy_port}")
                try:
                    response = await request_with_strategy(
                        "GET",
                        url,
                        strategy=ProxyStrategy.SMART,
                        timeout=1.0,
                    )
                    assert response.status_code == 200
                    assert response.text == "via-proxy"
                    await response.aclose()
                finally:
                    await egress_prefer_proxy_delete(origin)

    @pytest.mark.asyncio
    async def test_unknown_strategy(self):
        """Тест неизвестной стратегии."""
        with pytest.raises(ValueError, match="Unknown strategy"):
            await request_with_strategy(
                "GET",
                "https://example.com",
                strategy="unknown",  # type: ignore
                timeout=10.0,
            )

    @pytest.mark.asyncio
    async def test_default_strategy_is_direct_first(self):
        """Тест что стратегия по умолчанию DIRECT_FIRST."""
        with patch("core.http.client.egress_prefer_proxy_get", new_callable=AsyncMock, return_value=False):
            with patch("core.http.client._request_direct_burst") as mock_direct:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_direct.return_value = mock_response

                response = await request_with_strategy(
                    "GET",
                    "https://example.com",
                    timeout=10.0,
                )

                assert response.status_code == 200
                mock_direct.assert_called_once()
