"""Тесты для программируемой стратегии прокси в HTTP клиенте."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.http.client import ProxyStrategy, request_with_strategy


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
    async def test_direct_first_fallback_to_direct_after_proxy(self):
        """Тест DIRECT_FIRST - прямой и прокси не удались, повторное прямое."""
        import httpx

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
