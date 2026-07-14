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
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Iterator

import httpx
import pytest
from httpx import AsyncClient, Timeout
from playwright.async_api import Page, expect

from core.logging import get_logger
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_HTTP_TIMEOUT = Timeout(20.0)
_log = get_logger(__name__)


def _frontend_api_origin(frontend_ui: AppUI) -> str:
    """Frontend HTTP API на localhost: Host не должен резолвиться в чужую company."""
    return f"http://localhost:{frontend_ui.spec.port}"


def _flows_api_origin(flows_ui: AppUI) -> str:
    """Flows HTTP API на localhost для embed с внешнего origin 127.0.0.1."""
    return f"http://localhost:{flows_ui.spec.port}"


@dataclass(frozen=True)
class _SessionTokenProxy:
    platform_base_url: str
    embed_id: str
    auth_headers: dict[str, str]


class _EmbedHostState:
    __slots__ = ("page_bytes", "token_bytes", "session_token_proxy")

    def __init__(
        self,
        page_bytes: bytes,
        token_bytes: bytes,
        session_token_proxy: _SessionTokenProxy | None = None,
    ) -> None:
        self.page_bytes = page_bytes
        self.token_bytes = token_bytes
        self.session_token_proxy = session_token_proxy


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
            body_raw = self.rfile.read(length) if length > 0 else b""
            if state.session_token_proxy is not None:
                payload = json.loads(body_raw.decode("utf-8"))
                proxy = state.session_token_proxy
                target_url = (
                    f"{proxy.platform_base_url.rstrip('/')}"
                    f"/frontend/api/embed/configs/{proxy.embed_id}/session-token"
                )
                with httpx.Client(timeout=20.0) as client:
                    platform_response = client.post(
                        target_url,
                        headers={
                            **proxy.auth_headers,
                            "Content-Type": "application/json",
                        },
                        json={
                            "origin": payload["origin"],
                            "expires_in_seconds": payload.get("expires_in_seconds", 300),
                        },
                    )
                self.send_response(platform_response.status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(platform_response.content)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(state.token_bytes)

        def log_message(self, _format: str, *_args: object) -> None:
            return None

    return EmbedHostHandler


@contextmanager
def _external_embed_origin(
    *,
    html_page_utf8: str,
    token_payload: dict | None = None,
    session_token_proxy: _SessionTokenProxy | None = None,
) -> Iterator[str]:
    page_bytes = html_page_utf8.encode("utf-8")
    token_bytes = json.dumps(token_payload or {}, ensure_ascii=False).encode("utf-8")
    state = _EmbedHostState(page_bytes, token_bytes, session_token_proxy)
    handler = _make_embed_host_handler(state)
    server = HTTPServer(("localhost", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield f"http://localhost:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def _build_embed_page_html(
    *,
    script_src: str,
    embed_id: str,
    flows_base: str,
    frontend_origin: str,
    company_id: str,
    show_launcher: bool,
) -> str:
    launcher_attr = "true" if show_launcher else "false"
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>e2e-embed-host</title></head><body>"
        '<script type="module"\n'
        f'  src="{html_stdlib.escape(script_src, quote=True)}"\n'
        f'  data-embed-id="{html_stdlib.escape(embed_id, quote=True)}"\n'
        '  data-assistant-title="E2E embed"\n'
        '  data-theme="dark"\n'
        '  data-locale="ru"\n'
        f'  data-show-launcher="{launcher_attr}"\n'
        f'  data-flows-base-url="{html_stdlib.escape(flows_base, quote=True)}"\n'
        f'  data-platform-ui-origin="{html_stdlib.escape(frontend_origin, quote=True)}"\n'
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


async def _create_embed_config(
    frontend_origin: str,
    auth_headers: dict[str, str],
    *,
    flow_id: str,
    unique_id: str,
    show_launcher: bool,
) -> str:
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
                "show_launcher": show_launcher,
                "assistant_title": "E2E embed",
                "interface_locale": "ru",
            },
        )
        assert create.status_code == 200, create.text
        return create.json()["embed_id"]


async def _delete_embed_config(
    frontend_origin: str,
    auth_headers: dict[str, str],
    embed_id: str,
) -> None:
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


async def _attach_embed_page_diagnostics(page: Page) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    network_events: list[str] = []

    def _on_console(msg) -> None:
        if msg.type == "error":
            errors.append(f"console.{msg.type}: {msg.text}")

    def _record_embed_request(req) -> None:
        if "/api/v1/embed/" in req.url or req.url.endswith("/api/chat-token"):
            network_events.append(f"request {req.method} {req.url}")

    def _record_embed_response(resp) -> None:
        if "/api/v1/embed/" in resp.url or resp.url.endswith("/api/chat-token"):
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
    return errors, network_events


async def _wait_humanitec_embed(page: Page, errors: list[str], network_events: list[str]) -> None:
    try:
        await page.wait_for_function(
            "typeof window.humanitecEmbed !== 'undefined' && window.humanitecEmbed && window.humanitecEmbed.element",
            timeout=60_000,
        )
    except Exception as exc:
        raise AssertionError(
            "humanitecEmbed не смонтировался\n"
            f"errors:\n{chr(10).join(errors) or '<empty>'}\n\n"
            f"network:\n{chr(10).join(network_events) or '<empty>'}"
        ) from exc


async def _send_embed_message(page: Page, user_line: str, network_events: list[str], errors: list[str]) -> None:
    root = page.locator("platform-chat")
    textarea = root.locator("flows-chat-input textarea")
    await expect(textarea).to_be_visible(timeout=30_000)
    await textarea.fill(user_line)
    send_btn = root.locator("flows-chat-input button.send-btn:not(.muted)").first
    await expect(send_btn).to_be_enabled(timeout=10_000)
    await send_btn.click()
    try:
        await expect(page.get_by_text(f"embed-ok:{user_line}", exact=True)).to_be_visible(timeout=120_000)
    except AssertionError as exc:
        root_text = await root.inner_text(timeout=5_000)
        raise AssertionError(
            "embed браузер: не получен ожидаемый A2A ответ\n"
            f"root_text:\n{root_text}\n\n"
            f"network:\n{chr(10).join(network_events) or '<empty>'}\n\n"
            f"errors:\n{chr(10).join(errors) or '<empty>'}"
        ) from exc


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
    user_line = f"browser-embed-msg-{unique_id}"

    frontend_origin = _frontend_api_origin(frontend_ui).rstrip("/")
    flows_public_base = _flows_api_origin(flows_ui).rstrip("/")
    script_src = f"{frontend_origin}/static/core/lib/embed-chat/humanitec-embed-autoload.js"
    flows_base = f"{flows_public_base}/flows"

    embed_id: str | None = None
    errors, network_events = await _attach_embed_page_diagnostics(page)

    async with AsyncClient(
        base_url=frontend_origin,
        follow_redirects=True,
        timeout=_HTTP_TIMEOUT,
    ) as fc:
        embed_id = await _create_embed_config(
            frontend_origin,
            auth_headers,
            flow_id=flow_id,
            unique_id=unique_id,
            show_launcher=True,
        )
        mint = await fc.post(
            f"/frontend/api/embed/configs/{embed_id}/session-token",
            headers=auth_headers,
            json={"expires_in_seconds": 300},
        )
        assert mint.status_code == 200, mint.text
        token_payload_for_host = {"token": mint.json()["token"]}

    page_html = _build_embed_page_html(
        script_src=script_src,
        embed_id=embed_id,
        flows_base=flows_base,
        frontend_origin=frontend_origin,
        company_id=company_id,
        show_launcher=True,
    )

    try:
        with _external_embed_origin(html_page_utf8=page_html, token_payload=token_payload_for_host) as host_origin:
            await page.goto(f"{host_origin}/", wait_until="domcontentloaded", timeout=60_000)
            await _wait_humanitec_embed(page, errors, network_events)
            await expect(page.locator("platform-chat")).to_be_attached(timeout=30_000)
            fab = page.locator("platform-chat").locator("button.fab").first
            await expect(fab).to_be_visible(timeout=30_000)
            await fab.click()
            await _send_embed_message(page, user_line, network_events, errors)
            if errors:
                pytest.fail("embed браузер: ошибки страницы/консоли:\n" + "\n".join(errors))
    finally:
        if embed_id is not None:
            await _delete_embed_config(frontend_origin, auth_headers, embed_id)


@pytest.mark.scenario(
    service="flows",
    tag="api",
    doc_slug="embed-agent-on-site",
    title="Встраиваем агента на сайт",
    description=(
        "**Для чего:** эта инструкция покажет, как разместить чат агента на внешнем "
        "сайте магазина через embed-виджет.\n\n"
        "**Какие проблемы решает:** гостевая ссылка открывает отдельную страницу, а "
        "нужен чат прямо на витрине «Зелёного сада».\n\n"
        "**Результат:** на странице сайта открыт виджет чата и получен ответ агента."
    ),
    title_en="Embed the agent on a site",
    description_en=(
        "**What for:** this guide shows how to place the agent chat on an external store "
        "site via an embed widget.\n\n"
        "**Problems it solves:** a guest link opens a separate page, but you need chat "
        "on the Green Garden storefront itself.\n\n"
        "**Result:** the site page shows the chat widget and receives an agent reply."
    ),
)
@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flows_embed_agent_on_site(
    scenario: ScenarioRecorder,
    page: Page,
    embed_browser_http_stack_ready,
    taskiq_worker,
    frontend_ui: AppUI,
    flows_ui: AppUI,
    embed_test_auth,
    unique_id: str,
) -> None:
    _ = embed_browser_http_stack_ready, taskiq_worker
    page.set_default_timeout(45_000)
    auth_headers, flow_id, company_id, _user_part = embed_test_auth
    user_line = f"embed-site-{unique_id}"

    frontend_origin = _frontend_api_origin(frontend_ui).rstrip("/")
    flows_public_base = _flows_api_origin(flows_ui).rstrip("/")
    script_src = f"{frontend_origin}/static/core/lib/embed-chat/humanitec-embed-autoload.js"
    flows_base = f"{flows_public_base}/flows"

    embed_id: str | None = None
    errors, network_events = await _attach_embed_page_diagnostics(page)
    try:
        embed_id = await _create_embed_config(
            frontend_origin,
            auth_headers,
            flow_id=flow_id,
            unique_id=unique_id,
            show_launcher=True,
        )
        await scenario.step(
            "Создайте embed-конфиг для агента",
            page,
            screenshot_name="embed-config-created",
            label_en="Create an embed config for the agent",
            details=(
                "В настройках платформы создайте конфиг встраиваемого виджета и "
                "привяжите его к агенту магазина. Это не гостевая ссылка из редактора — "
                "виджет живёт на вашем сайте."
            ),
            details_en=(
                "In platform settings create an embed widget config and link it to the "
                "store agent. This is not the editor guest link — the widget lives on "
                "your site."
            ),
        )

        async with AsyncClient(
            base_url=frontend_origin,
            follow_redirects=True,
            timeout=_HTTP_TIMEOUT,
        ) as fc:
            mint = await fc.post(
                f"/frontend/api/embed/configs/{embed_id}/session-token",
                headers=auth_headers,
                json={"expires_in_seconds": 300},
            )
            assert mint.status_code == 200, mint.text
            token_payload_for_host = {"token": mint.json()["token"]}

        page_html = _build_embed_page_html(
            script_src=script_src,
            embed_id=embed_id,
            flows_base=flows_base,
            frontend_origin=frontend_origin,
            company_id=company_id,
            show_launcher=True,
        )
        await scenario.step(
            "Подготовьте страницу сайта со скриптом",
            page,
            screenshot_name="embed-host-ready",
            label_en="Prepare the site page with the script",
            details=(
                "На сайт магазина добавьте snippet autoload-скрипта с id виджета. "
                "Чат смонтируется на внешней странице витрины."
            ),
            details_en=(
                "Add the autoload script snippet with the widget id to the store site. "
                "Chat mounts on the external storefront page."
            ),
        )

        with _external_embed_origin(
            html_page_utf8=page_html,
            token_payload=token_payload_for_host,
        ) as host_origin:
            await page.goto(f"{host_origin}/", wait_until="domcontentloaded", timeout=60_000)
            await _wait_humanitec_embed(page, errors, network_events)
            await expect(page.locator("platform-chat")).to_be_attached(timeout=30_000)
            fab = page.locator("platform-chat").locator("button.fab").first
            await expect(fab).to_be_visible(timeout=30_000)
            await scenario.step(
                "Откройте виджет чата на сайте",
                page,
                screenshot_name="embed-fab-on-host",
                label_en="Open the chat widget on the site",
                details=(
                    "На странице сайта видна кнопка чата. Нажмите её — откроется диалог "
                    "с агентом прямо на витрине."
                ),
                details_en=(
                    "The site page shows a chat button. Click it — the agent dialog opens "
                    "on the storefront."
                ),
            )

            await fab.click()
            await _send_embed_message(page, user_line, network_events, errors)
            if errors:
                pytest.fail("embed браузер: ошибки страницы/консоли:\n" + "\n".join(errors))
            reply = page.locator("platform-chat").get_by_text(
                re.compile(rf"embed-ok:{re.escape(user_line)}", re.I)
            ).first
            await expect(reply).to_be_visible(timeout=120_000)
            await scenario.step(
                "Получите ответ агента во встроенном чате",
                page,
                screenshot_name="embed-reply-on-host",
                label_en="Get the agent reply in the embedded chat",
                details=(
                    "**Демонстрация результата.** Покупатель пишет на сайте магазина и "
                    "получает ответ агента во встроенном виджете — это embed, а не "
                    "гостевая ссылка.\n\n"
                    "**Итог.** Вы умеете создать embed-конфиг и проверить чат на "
                    "внешней странице."
                ),
                details_en=(
                    "**Result demonstration.** The customer writes on the store site and "
                    "gets an agent reply in the embedded widget — this is embed, not a "
                    "guest link.\n\n"
                    "**Summary.** You can create an embed config and verify chat on an "
                    "external page."
                ),
            )
    finally:
        if embed_id is not None:
            await _delete_embed_config(frontend_origin, auth_headers, embed_id)


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_embed_autoload_toggle_opens_chat_without_launcher(
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
    user_line = f"browser-embed-toggle-{unique_id}"

    frontend_origin = _frontend_api_origin(frontend_ui).rstrip("/")
    flows_public_base = _flows_api_origin(flows_ui).rstrip("/")
    script_src = f"{frontend_origin}/static/core/lib/embed-chat/humanitec-embed-autoload.js"
    flows_base = f"{flows_public_base}/flows"

    embed_id: str | None = None
    errors, network_events = await _attach_embed_page_diagnostics(page)

    async with AsyncClient(
        base_url=frontend_origin,
        follow_redirects=True,
        timeout=_HTTP_TIMEOUT,
    ) as fc:
        embed_id = await _create_embed_config(
            frontend_origin,
            auth_headers,
            flow_id=flow_id,
            unique_id=f"toggle-{unique_id}",
            show_launcher=False,
        )
        mint = await fc.post(
            f"/frontend/api/embed/configs/{embed_id}/session-token",
            headers=auth_headers,
            json={"expires_in_seconds": 300},
        )
        assert mint.status_code == 200, mint.text
        token_payload_for_host = {"token": mint.json()["token"]}

    page_html = _build_embed_page_html(
        script_src=script_src,
        embed_id=embed_id,
        flows_base=flows_base,
        frontend_origin=frontend_origin,
        company_id=company_id,
        show_launcher=False,
    )

    try:
        with _external_embed_origin(html_page_utf8=page_html, token_payload=token_payload_for_host) as host_origin:
            await page.goto(f"{host_origin}/", wait_until="domcontentloaded", timeout=60_000)
            await _wait_humanitec_embed(page, errors, network_events)
            fab = page.locator("platform-chat").locator("button.fab")
            await expect(fab).to_have_count(0, timeout=10_000)
            await page.evaluate(
                """() => {
                    window.dispatchEvent(
                        new CustomEvent('humanitec-embed-chat-toggle', { detail: { open: true } }),
                    );
                }"""
            )
            await _send_embed_message(page, user_line, network_events, errors)
            if errors:
                pytest.fail("embed toggle: ошибки страницы/консоли:\n" + "\n".join(errors))
    finally:
        if embed_id is not None:
            await _delete_embed_config(frontend_origin, auth_headers, embed_id)


@pytest.mark.timeout(300)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_embed_autoload_host_proxy_mints_session_token_s2s(
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
    user_line = f"browser-embed-proxy-{unique_id}"

    frontend_origin = _frontend_api_origin(frontend_ui).rstrip("/")
    flows_public_base = _flows_api_origin(flows_ui).rstrip("/")
    script_src = f"{frontend_origin}/static/core/lib/embed-chat/humanitec-embed-autoload.js"
    flows_base = f"{flows_public_base}/flows"

    embed_id = await _create_embed_config(
        frontend_origin,
        auth_headers,
        flow_id=flow_id,
        unique_id=f"proxy-{unique_id}",
        show_launcher=True,
    )
    errors, network_events = await _attach_embed_page_diagnostics(page)

    page_html = _build_embed_page_html(
        script_src=script_src,
        embed_id=embed_id,
        flows_base=flows_base,
        frontend_origin=frontend_origin,
        company_id=company_id,
        show_launcher=True,
    )
    session_proxy = _SessionTokenProxy(
        platform_base_url=frontend_origin,
        embed_id=embed_id,
        auth_headers=auth_headers,
    )

    try:
        with _external_embed_origin(
            html_page_utf8=page_html,
            session_token_proxy=session_proxy,
        ) as host_origin:
            await page.goto(f"{host_origin}/", wait_until="domcontentloaded", timeout=60_000)
            await _wait_humanitec_embed(page, errors, network_events)
            fab = page.locator("platform-chat").locator("button.fab").first
            await expect(fab).to_be_visible(timeout=30_000)
            await fab.click()
            await _send_embed_message(page, user_line, network_events, errors)
            chat_token_requests = [line for line in network_events if "/api/chat-token" in line]
            assert chat_token_requests, "autoload должен запросить /api/chat-token у mock host"
            if errors:
                pytest.fail("embed proxy S2S: ошибки страницы/консоли:\n" + "\n".join(errors))
    finally:
        await _delete_embed_config(frontend_origin, auth_headers, embed_id)
