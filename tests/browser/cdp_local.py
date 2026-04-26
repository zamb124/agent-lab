"""
Локальный CDP для тестов browser runtime.

Если переменная окружения BROWSER__CDP_URL задана — используем её как есть.
Иначе поднимаем headless Chromium локально с включённым CDP (remote debugging)
и возвращаем ws endpoint вида ``ws://127.0.0.1:<port>/devtools/browser/<id>``.
"""

from __future__ import annotations

import os
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from playwright.async_api import async_playwright


def _env_cdp_url() -> str | None:
    v = os.environ.get("BROWSER__CDP_URL", "").strip()
    return v or None


def _pick_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])
    finally:
        s.close()


@asynccontextmanager
async def ensure_cdp_url() -> AsyncIterator[str]:
    """
    Гарантирует доступный CDP URL для connect_over_cdp.

    - Если задан BROWSER__CDP_URL — yield его.
    - Иначе поднимает локальный Chromium с remote-debugging-port и yield ws endpoint.
    """

    existing = _env_cdp_url()
    if existing is not None:
        yield existing
        return

    port = _pick_free_port()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[f"--remote-debugging-port={port}"],
        )
        try:
            version_url = f"http://127.0.0.1:{port}/json/version"
            async with httpx.AsyncClient(timeout=10.0) as ac:
                r = await ac.get(version_url)
                r.raise_for_status()
                data = r.json()
            ws = data.get("webSocketDebuggerUrl")
            if not isinstance(ws, str) or not ws.strip():
                raise RuntimeError(f"json/version не вернул webSocketDebuggerUrl: {data!r}")
            yield ws.strip()
        finally:
            await browser.close()

