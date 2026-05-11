"""Вспомогательные фикстуры для тестов HTTP-клиента без сети."""

from __future__ import annotations

from collections.abc import Callable

import httpx

_ORIGINAL_ASYNC_CLIENT = httpx.AsyncClient


def install_mock_httpx_client(
    monkeypatch: object,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    """
    Подменяет httpx.AsyncClient в core.http.client так, что по умолчанию
    используется MockTransport с переданным handler.
    """

    transport = httpx.MockTransport(handler)

    def factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs.setdefault("transport", transport)
        return _ORIGINAL_ASYNC_CLIENT(*args, **kwargs)

    monkeypatch.setattr("core.http.client.httpx.AsyncClient", factory)
