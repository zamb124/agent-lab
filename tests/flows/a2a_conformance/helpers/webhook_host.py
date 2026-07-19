"""Ephemeral webhook receiver for push notification conformance."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from aiohttp import web

from core.types import JsonObject, require_json_object


@dataclass
class WebhookHost:
    base_url: str
    path: str = "/a2a-push"
    payloads: list[JsonObject] = field(default_factory=list)
    _event: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def url(self) -> str:
        return f"{self.base_url}{self.path}"

    async def wait_payload(self, *, timeout: float = 15.0) -> JsonObject:
        await asyncio.wait_for(self._event.wait(), timeout=timeout)
        if not self.payloads:
            raise AssertionError("webhook fired without payload")
        return self.payloads[-1]


@asynccontextmanager
async def serve_webhook() -> AsyncIterator[WebhookHost]:
    host = WebhookHost(base_url="")
    app = web.Application()

    async def handler(request: web.Request) -> web.Response:
        payload = require_json_object(await request.json(), "webhook.payload")
        host.payloads.append(payload)
        host._event.set()
        return web.Response(text="ok")

    app.router.add_post(host.path, handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    try:
        sockets = site._server.sockets  # type: ignore[attr-defined]
        if not sockets:
            raise RuntimeError("webhook host failed to bind")
        port = sockets[0].getsockname()[1]
        host.base_url = f"http://127.0.0.1:{port}"
        yield host
    finally:
        await runner.cleanup()
