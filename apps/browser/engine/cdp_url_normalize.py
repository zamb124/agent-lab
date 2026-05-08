"""Нормализация CDP URL для Playwright ``connect_over_cdp``.

``BrowserType.connect_over_cdp`` ожидает WebSocket debugger URL вида
``ws://host:port/devtools/browser/<id>``. Строка ``http://host:port`` или голый
``ws://host:port`` приводит к запросу ``ws://host:port/`` и ответу 404 от CDP.
"""

from __future__ import annotations

import json
from urllib.parse import urlparse, urlunparse

import httpx


async def fetch_browser_web_socket_debugger_url(
    http_base: str,
    *,
    http_timeout_s: float = 5.0,
) -> str:
    """GET ``{http_base}/json/version`` и поле ``webSocketDebuggerUrl``."""
    base = http_base.strip().rstrip("/")
    if base == "":
        raise ValueError("http_base для CDP discovery не может быть пустым")
    version_url = f"{base}/json/version"
    async with httpx.AsyncClient(timeout=http_timeout_s) as client:
        response = await client.get(version_url)
        response.raise_for_status()
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"CDP json/version по {version_url!r} не JSON: {response.text[:500]!r}"
            ) from exc
    ws = data.get("webSocketDebuggerUrl")
    if not isinstance(ws, str) or ws.strip() == "":
        raise RuntimeError(
            f"Ответ json/version по {version_url!r} без webSocketDebuggerUrl: {data!r}"
        )
    return ws.strip()


async def normalize_playwright_cdp_connect_url(
    url: str,
    *,
    http_timeout_s: float = 5.0,
) -> str:
    """Привести конфигурационный CDP URL к строке, пригодной для ``connect_over_cdp``."""
    raw = url.strip()
    if raw == "":
        raise ValueError("cdp_url не может быть пустым")
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme in ("http", "https"):
        if parsed.netloc == "":
            raise ValueError(f"CDP URL без netloc: {raw!r}")
        http_base = urlunparse((scheme, parsed.netloc, "", "", "", "")).rstrip("/")
        return await fetch_browser_web_socket_debugger_url(
            http_base,
            http_timeout_s=http_timeout_s,
        )
    if scheme in ("ws", "wss"):
        path = parsed.path or ""
        if "/devtools/browser/" in path:
            return raw
        if parsed.netloc == "":
            raise ValueError(f"CDP URL без netloc: {raw!r}")
        http_scheme = "https" if scheme == "wss" else "http"
        http_base = urlunparse((http_scheme, parsed.netloc, "", "", "", "")).rstrip("/")
        return await fetch_browser_web_socket_debugger_url(
            http_base,
            http_timeout_s=http_timeout_s,
        )
    raise ValueError(
        f"CDP URL для Playwright: ожидается http(s):// или ws(s)://; получено {raw!r}"
    )
