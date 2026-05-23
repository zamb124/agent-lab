"""Браузерный E2E: страница «внешнего сайта» + humanitec-embed-autoload.js при реальных HTTP-сервисах.

Поднимает flows (9001) и frontend (9004) через фикстуры session-серверов pytest
(``tests/fixtures/services.py``). Первый холодный прогон часто упирается в
``flows_service`` (``startup_wait`` до 120 с) и ``frontend_service`` (~20 с) до первой строки теста.

Диагностика: ``pytest ... --setup-show -v``, логи uvicorn при падении —
``/tmp/flows_server_test_err.log``, ``/tmp/frontend_server_test_err.log``.
Без браузера: ``tests/flows/e2e/test_embed_stream.py``.
"""

from __future__ import annotations

import html as html_stdlib
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Iterator

import pytest
from httpx import AsyncClient, Timeout
from playwright.async_api import Page, expect

from core.logging import get_logger
from tests.ui.harness import AppUI

_HTTP_TIMEOUT = Timeout(20.0)
_log = get_logger(__name__)


class _EmbedHostState:
    __slots__ = ("page_bytes", "token_bytes")

    def __init__(self, page_bytes: bytes, token_bytes: bytes) -> None:
        self.page_bytes = page_bytes
        self.token_bytes = token_bytes


def _make_embed_host_handler(state: _EmbedHostState) -> type[BaseHTTPRequestHandler]:
    class EmbedHostHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            raw = self.path.split("?", 1)[0].rstrip("/") or "/"
            if raw != "/":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(state.page_bytes)

        def do_POST(self) -> None:
            raw = self.path.split("?", 1)[0].rstrip("/") or ""
            if raw != "/api/chat-token":
                self.send_error(404)
                return
            length_hdr = self.headers.get("Content-Length")
            length = int(length_hdr) if length_hdr and length_hdr.isdigit() else 0
            _ = self.rfile.read(length) if length > 0 else b""
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(state.token_bytes)

        def log_message(self, _format: str, *_args: object) -> None:
            return None

    return EmbedHostHandler


@contextmanager
def _external_embed_origin(*, html_page_utf8: str, token_payload: dict) -> Iterator[str]:
    page_bytes = html_page_utf8.encode("utf-8")
    token_bytes = json.dumps(token_payload, ensure_ascii=False).encode("utf-8")
    state = _EmbedHostState(page_bytes, token_bytes)
    handler = _make_embed_host_handler(state)
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_embed_autoload_script_mounts_chat_and_streams_reply(
    page: Page,
    embed_browser_http_stack_ready,
    taskiq_worker,
    frontend_ui: AppUI,
    flows_ui: AppUI,
    embed_test_auth,
    unique_id: str,
) -> None:
    page.set_default_timeout(45_000)
    auth_headers, flow_id, company_id, _user_part = embed_test_auth
    _log.info(
        "embed_browser_e2e: тело теста frontend=%s flows=%s",
        frontend_ui.origin,
        flows_ui.origin,
    )
    user_line = f"browser-embed-msg-{unique_id}"

    frontend_origin = frontend_ui.origin.rstrip("/")
    flows_public_base = flows_ui.origin.rstrip("/")
    script_src = f"{frontend_origin}/static/core/lib/embed-chat/humanitec-embed-autoload.js"
    flows_base = f"{flows_public_base}/flows"

    embed_id: str | None = None

    errors: list[str] = []
    network_events: list[str] = []

    def _on_console(msg) -> None:
        if msg.type == "error":
            errors.append(f"console.{msg.type}: {msg.text}")

    def _record_embed_request(req) -> None:
        if "/api/v1/embed/" in req.url:
            network_events.append(f"request {req.method} {req.url}")

    def _record_embed_response(resp) -> None:
        if "/api/v1/embed/" in resp.url:
            network_events.append(f"response {resp.status} {resp.url}")

    await page.add_init_script(
        """
        window.addEventListener('error', (event) => {
            console.error(
                '[embed-e2e-window-error]',
                event.filename || '<inline>',
                event.lineno || 0,
                event.colno || 0,
                event.message || '',
                event.error && event.error.stack ? event.error.stack : ''
            );
        });
        """
    )

    def _on_pageerror(exc) -> None:
        stack = getattr(exc, "stack", None)
        errors.append(f"pageerror: {exc}\n{stack}" if stack else f"pageerror: {exc}")

    page.on("pageerror", _on_pageerror)
    page.on("console", _on_console)
    page.on("request", _record_embed_request)
    page.on("response", _record_embed_response)

    async with AsyncClient(
        base_url=frontend_origin,
        follow_redirects=True,
        timeout=_HTTP_TIMEOUT,
    ) as fc:
        create = await fc.post(
            "/frontend/api/embed/configs",
            headers=auth_headers,
            json={
                "name": f"Embed browser {unique_id}",
                "flow_id": flow_id,
                "allowed_origins": [],
                "theme": "dark",
                "show_launcher": True,
                "assistant_title": "E2E embed",
                "interface_locale": "ru",
            },
        )
        assert create.status_code == 200, create.text
        embed_id = create.json()["embed_id"]

        mint = await fc.post(
            f"/frontend/api/embed/configs/{embed_id}/session-token",
            headers=auth_headers,
            json={"expires_in_seconds": 300},
        )
        assert mint.status_code == 200, mint.text
        token_body = mint.json()
        embed_token = token_body["token"]
        token_payload_for_host = {"token": embed_token}

    assert embed_id is not None
    _log.info("embed_browser_e2e: конфиг виджета и embed-session token получены embed_id=%s", embed_id)

    page_html = (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>e2e-embed-host</title></head><body>"
        '<script type="module"\n'
        f'  src="{html_stdlib.escape(script_src, quote=True)}"\n'
        f'  data-embed-id="{html_stdlib.escape(embed_id, quote=True)}"\n'
        '  data-assistant-title="E2E embed"\n'
        '  data-theme="dark"\n'
        '  data-locale="ru"\n'
        '  data-show-launcher="true"\n'
        f'  data-flows-base-url="{html_stdlib.escape(flows_base, quote=True)}"\n'
        '  data-chat-token-url="/api/chat-token"\n'
        '  data-token-expires-seconds="300"\n'
        '  data-use-credentials="false"\n'
        '  data-event-namespace="assistant"\n'
        '  data-toggle-event-name="humanitec-embed-chat-toggle"\n'
        '  data-voice-enabled="false"\n'
        '  data-voice-default-on="false"\n'
        f'  data-voice-base-url="{html_stdlib.escape(f"{frontend_origin}/voice", quote=True)}"\n'
        f'  data-company-id="{html_stdlib.escape(company_id, quote=True)}"\n'
        "></script></body></html>"
    )

    try:
        with _external_embed_origin(html_page_utf8=page_html, token_payload=token_payload_for_host) as host_origin:
            _log.info("embed_browser_e2e: открываем хост %s скрипт %s", host_origin, script_src)
            await page.goto(f"{host_origin}/", wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_function(
                "typeof window.humanitecEmbed !== 'undefined' && window.humanitecEmbed && window.humanitecEmbed.element",
                timeout=60_000,
            )
            _log.info("embed_browser_e2e: humanitecEmbed смонтирован")
            await expect(page.locator("platform-lara-assistant")).to_be_visible(timeout=30_000)
            fab = page.locator("platform-lara-assistant").locator("button.fab").first
            await expect(fab).to_be_visible(timeout=30_000)
            await fab.click()
            root = page.locator("platform-lara-assistant")
            textarea = root.locator("embed-chat-input textarea")
            await expect(textarea).to_be_visible(timeout=30_000)
            await textarea.fill(user_line)
            send_btn = root.locator("embed-chat-input button.send-btn:not(.muted)").first
            await expect(send_btn).to_be_enabled(timeout=10_000)
            await send_btn.click()
            _log.info("embed_browser_e2e: сообщение отправлено, ждём ответ потока A2A")
            try:
                await expect(page.get_by_text(f"embed-ok:{user_line}", exact=True)).to_be_visible(
                    timeout=90_000
                )
            except AssertionError as exc:
                root_text = await root.inner_text(timeout=5_000)
                raise AssertionError(
                    "embed браузер: не получен ожидаемый A2A ответ\n"
                    f"root_text:\n{root_text}\n\n"
                    f"network:\n{chr(10).join(network_events) or '<empty>'}\n\n"
                    f"errors:\n{chr(10).join(errors) or '<empty>'}"
                ) from exc
            _log.info("embed_browser_e2e: ответ агента в UI получен")
            if errors:
                pytest.fail("embed браузер: ошибки страницы/консоли:\n" + "\n".join(errors))
    finally:
        if embed_id is None:
            return
        try:
            async with AsyncClient(
                base_url=frontend_origin,
                follow_redirects=True,
                timeout=_HTTP_TIMEOUT,
            ) as fc_delete:
                del_r = await fc_delete.delete(
                    f"/frontend/api/embed/configs/{embed_id}",
                    headers=auth_headers,
                )
                assert del_r.status_code == 200
        except Exception:
            _log.exception("embed_browser_e2e: cleanup embed config failed embed_id=%s", embed_id)
