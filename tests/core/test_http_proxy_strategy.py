"""Тесты для программируемой стратегии прокси в HTTP клиенте."""

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from core.http.client import ProxyStrategy, get_httpx_client, request_with_strategy


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
        import httpx

        with patch("core.http.client._request_direct_burst") as mock_direct:
            mock_direct.side_effect = httpx.ConnectError("Connection failed")

            with pytest.raises(httpx.ConnectError):
                await request_with_strategy(
                    "GET",
                    "https://example.com",
                    strategy=ProxyStrategy.DIRECT_ONLY,
                    direct_attempts=2,
                    timeout=10.0,
                )

            mock_direct.assert_called_once()

    @pytest.mark.asyncio
    async def test_proxy_only_with_active_proxy(self):
        """Тест PROXY_ONLY - прокси активен."""
        with patch("core.http.client._platform_proxy_active", return_value=True):
            with patch("core.http.client.get_httpx_client") as mock_get_client:
                mock_client = AsyncMock()
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_client.request.return_value = mock_response
                mock_get_client.return_value.__aenter__.return_value = mock_client

                response = await request_with_strategy(
                    "GET",
                    "https://example.com",
                    strategy=ProxyStrategy.PROXY_ONLY,
                    proxy_attempts=3,
                    timeout=10.0,
                )

                assert response.status_code == 200
                mock_get_client.assert_called_once()
                call_kwargs = mock_get_client.call_args[1]
                assert call_kwargs["strategy"] == ProxyStrategy.PROXY_ONLY
                assert call_kwargs["proxy_attempts"] == 3

    @pytest.mark.asyncio
    async def test_proxy_only_without_proxy_configured(self):
        """Тест PROXY_ONLY - прокси не настроен."""
        import httpx

        with patch("core.http.client._platform_proxy_active", return_value=False):
            with pytest.raises(httpx.ConnectError, match="Proxy requested but not configured"):
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
    async def test_direct_first_fallback_to_proxy(self):
        """Тест DIRECT_FIRST - прямой запрос не удался, fallback на прокси."""
        import httpx

        with patch("core.http.client.egress_prefer_proxy_get", new_callable=AsyncMock, return_value=False):
            with patch("core.http.client._request_direct_burst") as mock_direct:
                with patch("core.http.client._platform_proxy_active", return_value=True):
                    with patch("core.http.client.get_httpx_client") as mock_get_client:
                        mock_direct.side_effect = httpx.ConnectError("Direct failed")

                        mock_client = AsyncMock()
                        mock_response = MagicMock()
                        mock_response.status_code = 200
                        mock_client.request.return_value = mock_response
                        mock_get_client.return_value.__aenter__.return_value = mock_client

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
                        mock_get_client.assert_called_once()

    @pytest.mark.asyncio
    async def test_direct_first_fallback_json_not_passed_to_httpx_client_ctor(self):
        """POST json к Telegram: fallback на прокси не должен пробрасывать json в AsyncClient."""
        import httpx

        with patch("core.http.client.egress_prefer_proxy_get", new_callable=AsyncMock, return_value=False):
            with patch("core.http.client._request_direct_burst") as mock_direct:
                with patch("core.http.client._platform_proxy_active", return_value=True):
                    with patch("core.http.client.get_httpx_client") as mock_get_client:
                        mock_direct.side_effect = httpx.ConnectError("Direct failed")

                        mock_client = AsyncMock()
                        mock_response = MagicMock()
                        mock_response.status_code = 200
                        mock_client.request.return_value = mock_response
                        mock_get_client.return_value.__aenter__.return_value = mock_client

                        payload = {"chat_id": "-1", "text": "x"}
                        response = await request_with_strategy(
                            "POST",
                            "https://api.telegram.org/botfake/sendMessage",
                            strategy=ProxyStrategy.DIRECT_FIRST,
                            direct_attempts=1,
                            proxy_attempts=3,
                            timeout=10.0,
                            json=payload,
                        )

                        assert response.status_code == 200
                        mock_get_client.assert_called_once()
                        client_call_kwargs = mock_get_client.call_args[1]
                        assert "json" not in client_call_kwargs
                        req_call = mock_client.request.await_args
                        assert req_call is not None
                        assert req_call.kwargs["json"] == payload

    @pytest.mark.asyncio
    async def test_direct_first_fallback_to_direct_after_proxy(self):
        """Тест DIRECT_FIRST - прямой и прокси не удались, повторное прямое."""
        import httpx

        with patch("core.http.client.egress_prefer_proxy_get", new_callable=AsyncMock, return_value=False):
            with patch("core.http.client._request_direct_burst") as mock_direct:
                with patch("core.http.client._platform_proxy_active", return_value=True):
                    with patch("core.http.client.get_httpx_client") as mock_get_client:
                        # Первый вызов _request_direct_burst падает
                        # Прокси тоже падает
                        # Второй вызов _request_direct_burst успешен
                        mock_direct.side_effect = [
                            httpx.ConnectError("Direct failed"),
                            MagicMock(status_code=200),
                        ]

                        mock_client = AsyncMock()
                        mock_client.request.side_effect = httpx.ConnectError("Proxy failed")
                        mock_get_client.return_value.__aenter__.return_value = mock_client

                        response = await request_with_strategy(
                            "GET",
                            "https://example.com",
                            strategy=ProxyStrategy.DIRECT_FIRST,
                            direct_attempts=3,
                            proxy_attempts=3,
                            timeout=10.0,
                        )

                        assert response.status_code == 200
                        assert mock_direct.call_count == 2

    @pytest.mark.asyncio
    async def test_proxy_first_success_on_proxy(self):
        """Тест PROXY_FIRST - успешный запрос через прокси."""
        with patch("core.http.client._platform_proxy_active", return_value=True):
            with patch("core.http.client.get_httpx_client") as mock_get_client:
                mock_client = AsyncMock()
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_client.request.return_value = mock_response
                mock_get_client.return_value.__aenter__.return_value = mock_client

                response = await request_with_strategy(
                    "GET",
                    "https://example.com",
                    strategy=ProxyStrategy.PROXY_FIRST,
                    proxy_attempts=3,
                    direct_attempts=2,
                    timeout=10.0,
                )

                assert response.status_code == 200
                mock_get_client.assert_called_once()

    @pytest.mark.asyncio
    async def test_proxy_first_fallback_to_direct(self):
        """Тест PROXY_FIRST - прокси не удался, fallback на прямое."""
        import httpx

        with patch("core.http.client._platform_proxy_active", return_value=True):
            with patch("core.http.client.get_httpx_client") as mock_get_client:
                with patch("core.http.client._request_direct_burst") as mock_direct:
                    mock_client = AsyncMock()
                    mock_client.request.side_effect = httpx.ConnectError("Proxy failed")
                    mock_get_client.return_value.__aenter__.return_value = mock_client

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
                    mock_get_client.assert_called_once()
                    mock_direct.assert_called_once()

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

            with patch("core.http.client.httpx.AsyncClient", FakeAsyncClient):
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
    async def test_egress_prefer_proxy_set_requires_ttl(self):
        """egress_prefer_proxy_set передаёт TTL в RedisClient.set."""
        from core.http.egress_route_preference import egress_prefer_proxy_set

        mock_rc = MagicMock()
        mock_rc.set = AsyncMock(return_value=True)

        with patch("core.http.egress_route_preference._redis_client", return_value=mock_rc):
            with patch(
                "core.http.egress_route_preference._platform_proxy_configured",
                return_value=True,
            ):
                with patch("core.http.egress_route_preference.get_settings") as mock_gs:
                    mock_gs.return_value.proxy.prefer_proxy_ttl_seconds = 3600
                    await egress_prefer_proxy_set("https://example.com:443")

        mock_rc.set.assert_awaited_once()
        assert mock_rc.set.call_args[1]["ttl"] == 3600

    @pytest.mark.asyncio
    async def test_smart_403_retries_via_proxy_when_configured(self):
        """SMART: 403 напрямую, затем успех через platform proxy."""
        first = MagicMock()
        first.status_code = 403
        first.aclose = AsyncMock()

        second = MagicMock()
        second.status_code = 200
        type(second).is_success = PropertyMock(return_value=True)

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
                with patch("core.http.client.httpx.AsyncClient", FakeAsyncClient):
                    with patch("core.http.client._platform_proxy_active", return_value=True):
                        with patch(
                            "core.http.client.SmartProxyClient._get_settings",
                            return_value=mock_settings,
                        ):
                            async with get_httpx_client(timeout=10.0, strategy=ProxyStrategy.SMART) as client:
                                r = await client.request("GET", "https://api.example.com/x")

        assert r.status_code == 200
        first.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_smart_403_no_proxy_when_not_configured(self):
        """SMART: 403 и прокси выключен — отдаём первый ответ."""
        first = MagicMock()
        first.status_code = 403
        first.aclose = AsyncMock()

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def request(self, method, url, **kwargs):
                return first

        with patch("core.http.client.httpx.AsyncClient", FakeAsyncClient):
            with patch("core.http.client._platform_proxy_active", return_value=False):
                async with get_httpx_client(timeout=10.0, strategy=ProxyStrategy.SMART) as client:
                    r = await client.request("GET", "https://api.example.com/x")

        assert r.status_code == 403
        first.aclose.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_request_with_strategy_smart_delegates(self):
        """request_with_strategy(SMART) дергает get_httpx_client со стратегией SMART."""
        with patch("core.http.client.get_httpx_client") as mock_get:
            mock_inner = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_inner.request.return_value = mock_resp
            mock_get.return_value.__aenter__.return_value = mock_inner

            response = await request_with_strategy(
                "GET",
                "https://example.com",
                strategy=ProxyStrategy.SMART,
                timeout=10.0,
            )

            assert response.status_code == 200
            mock_get.assert_called_once()
            assert mock_get.call_args[1]["strategy"] == ProxyStrategy.SMART

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
