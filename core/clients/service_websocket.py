"""Межсервисный WebSocket: flows LSP proxy → code-runner language server."""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import websockets
from fastapi import WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed
from websockets.protocol import State

from core.config import get_settings
from core.logging import get_logger
from core.utils.background import run_with_log_context

logger = get_logger(__name__)


def _websocket_close_code(exc: ConnectionClosed) -> int:
    received = exc.rcvd
    if received is not None:
        return received.code
    sent = exc.sent
    if sent is not None:
        return sent.code
    return 1011


async def proxy_service_websocket(client_ws: WebSocket, service: str, path: str) -> None:
    """Проксирует JSON-текст кадры на peer-сервис. Не httpx."""
    settings = get_settings()
    base = settings.server.get_service_url(service).rstrip("/")
    parsed = urlparse(base)
    if parsed.netloc == "":
        raise RuntimeError(f"service websocket url missing host: {service}")
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    upstream_url = f"{ws_scheme}://{parsed.netloc}{path}"
    await client_ws.accept()
    try:
        upstream = await websockets.connect(
            upstream_url,
            open_timeout=10,
            ping_interval=None,
            max_size=None,
        )
    except websockets.ConnectionClosed as exc:
        await client_ws.close(code=_websocket_close_code(exc))
        return
    except Exception as exc:
        logger.exception("service_websocket.upstream_failed", service=service, path=path)
        await client_ws.close(code=1011)
        raise RuntimeError(f"language server websocket failed: {service}") from exc
    already_closed = upstream.close_code
    if already_closed is not None:
        await client_ws.close(code=already_closed)
        await upstream.close()
        return
    if upstream.state is not State.OPEN:
        await upstream.wait_closed()
        close_code = upstream.close_code
        await client_ws.close(code=close_code if close_code is not None else 1011)
        await upstream.close()
        return

    async def client_to_upstream() -> None:
        try:
            while True:
                payload = await client_ws.receive_text()
                await upstream.send(payload)
        except WebSocketDisconnect:
            await upstream.close()
        except websockets.ConnectionClosed:
            return

    async def upstream_to_client() -> None:
        try:
            async for frame in upstream:
                if isinstance(frame, bytes):
                    await client_ws.send_bytes(frame)
                else:
                    await client_ws.send_text(frame)
        except websockets.ConnectionClosed as exc:
            try:
                await client_ws.close(code=_websocket_close_code(exc))
            except RuntimeError:
                return
            return

    async def upstream_closed() -> None:
        await upstream.wait_closed()
        close_code = upstream.close_code
        try:
            await client_ws.close(code=close_code if close_code is not None else 1011)
        except RuntimeError:
            return

    try:
        done, pending = await asyncio.wait(
            {
                run_with_log_context(
                    client_to_upstream(),
                    name="service_websocket.client_to_upstream",
                    background_kind="code_lsp",
                ),
                run_with_log_context(
                    upstream_to_client(),
                    name="service_websocket.upstream_to_client",
                    background_kind="code_lsp",
                ),
                run_with_log_context(
                    upstream_closed(),
                    name="service_websocket.upstream_closed",
                    background_kind="code_lsp",
                ),
            },
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            _ = task.cancel()
        for task in pending:
            try:
                await task
            except asyncio.CancelledError:
                pass
        for task in done:
            exc = task.exception()
            if exc is not None:
                raise exc
    finally:
        await upstream.close()
        try:
            await client_ws.close()
        except RuntimeError as exc:
            logger.info("service_websocket.client_already_closed", error=str(exc))
