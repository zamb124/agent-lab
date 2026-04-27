"""
Локальный CDP для тестов browser runtime.

Поднимает Lightpanda в Docker и возвращает ws endpoint вида
``ws://127.0.0.1:9222/devtools/browser/<id>``.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from apps.browser.config import get_browser_settings


@asynccontextmanager
async def ensure_cdp_url() -> AsyncIterator[str]:
    """
    Гарантирует доступный CDP URL для connect_over_cdp.

    - Если в настройках задан `browser.e2e_lightpanda_cdp_url` — yield его.
    - Иначе поднимает Lightpanda в Docker и yield ws endpoint.
    """

    settings = get_browser_settings()
    existing = settings.browser.e2e_lightpanda_cdp_url.strip()
    if existing:
        yield existing
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
        version_url = "http://127.0.0.1:9222/json/version"
        deadline = time.monotonic() + 30.0
        last_error: Exception | None = None

        async with httpx.AsyncClient(timeout=2.0) as ac:
            while time.monotonic() < deadline:
                if proc.returncode is not None:
                    raise RuntimeError("Lightpanda Docker-контейнер завершился до готовности CDP")
                try:
                    r = await ac.get(version_url)
                    r.raise_for_status()
                    data = r.json()
                    ws = data.get("webSocketDebuggerUrl")
                    if not isinstance(ws, str) or not ws.strip():
                        raise RuntimeError(
                            f"json/version не вернул webSocketDebuggerUrl: {data!r}"
                        )
                    yield ws.strip()
                    return
                except (httpx.HTTPError, json.JSONDecodeError, RuntimeError) as e:
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

