"""
Локальный CDP для тестов browser runtime.

Поднимает Lightpanda в Docker и возвращает ws endpoint вида
``ws://127.0.0.1:9222/devtools/browser/<id>``.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from apps.browser.config import get_browser_settings
from apps.browser.engine.cdp_url_normalize import (
    fetch_browser_web_socket_debugger_url,
    normalize_playwright_cdp_connect_url,
)


@asynccontextmanager
async def ensure_cdp_url() -> AsyncIterator[str]:
    """
    Гарантирует доступный CDP URL для connect_over_cdp.

    - Если в настройках задан `browser.e2e_lightpanda_cdp_url` — yield нормализованный ws endpoint.
    - Иначе поднимает Lightpanda в Docker и yield ws endpoint.
    """

    settings = get_browser_settings()
    existing = settings.browser.e2e_lightpanda_cdp_url.strip()
    if existing:
        yield await normalize_playwright_cdp_connect_url(existing, http_timeout_s=5.0)
        return

    proc = await asyncio.create_subprocess_exec(
        "docker",
        "run",
        "--rm",
        "-p",
        "9222:9222",
        "lightpanda/browser:nightly",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30.0
        last_error: Exception | None = None

        while time.monotonic() < deadline:
            if proc.returncode is not None:
                raise RuntimeError("Lightpanda Docker-контейнер завершился до готовности CDP")
            try:
                ws = await fetch_browser_web_socket_debugger_url(
                    "http://127.0.0.1:9222",
                    http_timeout_s=2.0,
                )
                yield ws
                return
            except (httpx.HTTPError, RuntimeError, ValueError) as e:
                last_error = e
                await asyncio.sleep(0.25)

        raise RuntimeError(f"Lightpanda CDP не поднялся за 30s: {last_error!r}")
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except TimeoutError:
                proc.kill()
                await proc.wait()

