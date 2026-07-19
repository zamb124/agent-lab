"""Ephemeral HTTP file host for Part.url inbound conformance tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from aiohttp import web


@dataclass(frozen=True, slots=True)
class FileHost:
    base_url: str
    path: str
    body: bytes
    content_type: str

    @property
    def url(self) -> str:
        return f"{self.base_url}{self.path}"


@asynccontextmanager
async def serve_file(
    *,
    body: bytes,
    content_type: str = "text/plain",
    path: str = "/fixture.txt",
) -> AsyncIterator[FileHost]:
    app = web.Application()

    async def handler(_request: web.Request) -> web.Response:
        return web.Response(body=body, content_type=content_type)

    app.router.add_get(path, handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    try:
        sockets = site._server.sockets  # type: ignore[attr-defined]
        if not sockets:
            raise RuntimeError("file host failed to bind")
        port = sockets[0].getsockname()[1]
        yield FileHost(
            base_url=f"http://127.0.0.1:{port}",
            path=path,
            body=body,
            content_type=content_type,
        )
    finally:
        await runner.cleanup()
