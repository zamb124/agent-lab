"""Вспомогательные функции для aiohttp TCPSite на свободном порту (xdist без коллизий)."""

from __future__ import annotations

import socket
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Protocol, cast

from aiohttp import web


class _ListeningServer(Protocol):
    sockets: list[socket.socket] | None


def tcp_site_assigned_port(site: web.TCPSite) -> int:
    server = cast(_ListeningServer | None, site._server)  # pyright: ignore[reportPrivateUsage]
    if server is None:
        raise RuntimeError("TCPSite не запущен")
    sockets = server.sockets
    if not sockets:
        raise RuntimeError("У сервера нет сокетов после start()")
    return cast(int, sockets[0].getsockname()[1])


@asynccontextmanager
async def ephemeral_web_server(
    app: web.Application,
    *,
    host: str = "127.0.0.1",
) -> AsyncGenerator[str]:
    """Поднимает app на свободном порту; в teardown — site.stop() и runner.cleanup()."""
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, 0)
    await site.start()
    port = tcp_site_assigned_port(site)
    base_url = f"http://{host}:{port}"
    try:
        yield base_url
    finally:
        await site.stop()
        await runner.cleanup()
