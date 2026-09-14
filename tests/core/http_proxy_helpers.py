"""Вспомогательные фикстуры для тестов HTTP-клиента без сети."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

_ORIGINAL_ASYNC_CLIENT = httpx.AsyncClient


def unread_json_response(
    request: httpx.Request,
    status_code: int,
    body: bytes,
) -> httpx.Response:
    """HTTP-ответ со stream-телом, которое ещё не прочитали через aread()."""
    return httpx.Response(
        status_code,
        headers={"content-type": "application/json"},
        stream=httpx.ByteStream(body),
        request=request,
    )


def install_mock_httpx_client(
    monkeypatch: pytest.MonkeyPatch,
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
