"""Мост WS браузера UI E2E: dev-URL Centrifugo → тестовый инстанс.

`ws.effect.ts` на локальных dev-хостах (*.lvh.me, *.localhost) открывает
`ws://<host>:8000/connection/websocket` — dev-инстанс Centrifugo с dev-секретом.
Тестовый стек держит свой Centrifugo (CENTRIFUGO_WS_URL, по умолчанию :19000)
под тестовым JWT-секретом. Мост на уровне e2e-окружения — аналог ingress в
проде, где `/realtime/connection/websocket` ведёт на Centrifugo, — перенаправляет
кадры на тестовый endpoint: реальное WS-соединение, без подмены транспорта.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress

import websockets
from playwright.async_api import BrowserContext, Error as PlaywrightError, WebSocketRoute

logger = logging.getLogger(__name__)

_CENTRIFUGO_WS_GLOB = "**/connection/websocket"
_DEFAULT_UPSTREAM_URL = "ws://127.0.0.1:19000/connection/websocket"


async def _send_upstream(upstream: websockets.ClientConnection, message: str | bytes) -> None:
    try:
        await upstream.send(message)
    except websockets.ConnectionClosed:
        return


async def _bridge_connection(ws_route: WebSocketRoute, upstream_url: str) -> None:
    try:
        upstream = await websockets.connect(
            upstream_url,
            subprotocols=list(ws_route.protocols) or None,
            ping_interval=None,
            max_size=None,
        )
    except (OSError, TimeoutError) as exc:
        logger.warning("ui e2e ws bridge: upstream %s unreachable: %s", upstream_url, exc)
        with suppress(PlaywrightError):
            await ws_route.close(code=1011, reason="test Centrifugo unreachable")
        return

    loop = asyncio.get_running_loop()

    async def _upstream_to_page() -> None:
        try:
            async for message in upstream:
                ws_route.send(message)
        except (websockets.ConnectionClosed, PlaywrightError):
            return

    pump = loop.create_task(_upstream_to_page())

    def _on_page_close(_code: int | None, _reason: str | None) -> None:
        pump.cancel()
        loop.create_task(upstream.close())

    def _on_pump_done(_task: asyncio.Task[None]) -> None:
        async def _finish() -> None:
            with suppress(PlaywrightError):
                await ws_route.close(code=1000)
            await upstream.close()

        loop.create_task(_finish())

    ws_route.on_message(lambda message: loop.create_task(_send_upstream(upstream, message)))
    ws_route.on_close(_on_page_close)
    pump.add_done_callback(_on_pump_done)


async def install_centrifugo_ws_bridge(context: BrowserContext) -> None:
    upstream_url = os.environ.get("CENTRIFUGO_WS_URL", _DEFAULT_UPSTREAM_URL)

    async def _handle(ws_route: WebSocketRoute) -> None:
        await _bridge_connection(ws_route, upstream_url)

    await context.route_web_socket(_CENTRIFUGO_WS_GLOB, _handle)
