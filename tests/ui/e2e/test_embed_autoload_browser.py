"""Браузерный E2E: страница «внешнего сайта» + flow-ui-embed-autoload.js при реальных HTTP-сервисах.

Поднимает flows (9001) и frontend (9004) через фикстуры session-серверов pytest
(``tests/fixtures/services.py``). Тело теста — бюджет 15 с (см. ``tests/ui/e2e/conftest.py``);
холодный startup сервисов в setup не входит в ``timeout_func_only``.

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
from urllib.parse import urlparse

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
            if raw in {"/favicon.ico", "/favicon.png"}:
                self.send_response(204)
                self.end_headers()
                return
            if raw != "/":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(state.page_bytes)

        def do_POST(self) -> None:
            raw = self.path.split("?", 1)[0].rstrip("/") or ""
            if raw != "/api/flow-ui-token":
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
    presentation: str = "drawer",
    position: str = "bottom-right",
    theme: str = "dark",
    locale: str = "ru",
    token_url: str | None = "/api/flow-ui-token",
    token_expires_seconds: str = "300",
    use_credentials: bool = False,
    toggle_event_name: str = "linnex-flow-ui-toggle",
    initial_open: bool = False,
) -> str:
    launcher_attr = "true" if show_launcher else "false"
    credentials_attr = "true" if use_credentials else "false"
    initial_open_attr = "true" if initial_open else "false"
    token_lines = ""
    if token_url is not None:
        token_lines = (
            f'  data-token-url="{html_stdlib.escape(token_url, quote=True)}"\n'
            f'  data-token-expires-seconds="{html_stdlib.escape(token_expires_seconds, quote=True)}"\n'
        )
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>e2e-embed-host</title></head><body>"
        '<script type="module"\n'
        f'  src="{html_stdlib.escape(script_src, quote=True)}"\n'
        f'  data-embed-id="{html_stdlib.escape(embed_id, quote=True)}"\n'
        f'  data-presentation="{html_stdlib.escape(presentation, quote=True)}"\n'
        f'  data-position="{html_stdlib.escape(position, quote=True)}"\n'
        f'  data-theme="{html_stdlib.escape(theme, quote=True)}"\n'
        f'  data-locale="{html_stdlib.escape(locale, quote=True)}"\n'
        f'  data-show-launcher="{launcher_attr}"\n'
        f'  data-initial-open="{initial_open_attr}"\n'
        f'  data-flows-base-url="{html_stdlib.escape(flows_base, quote=True)}"\n'
        f'  data-platform-ui-origin="{html_stdlib.escape(frontend_origin, quote=True)}"\n'
        f'{token_lines}'
        f'  data-use-credentials="{credentials_attr}"\n'
        f'  data-toggle-event-name="{html_stdlib.escape(toggle_event_name, quote=True)}"\n'
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


_EMBED_HOST_BENIGN_404_PATHS = frozenset({
    "/favicon.ico",
    "/favicon.png",
    "/apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png",
    "/robots.txt",
    "/manifest.json",
})


def _is_benign_embed_host_404(url: str) -> bool:
    path = urlparse(url).path.rstrip("/") or "/"
    return path in _EMBED_HOST_BENIGN_404_PATHS


async def _attach_embed_page_diagnostics(
    page: Page,
) -> tuple[list[str], list[str], list[str], list[str]]:
    errors: list[str] = []
    network_events: list[str] = []
    static_urls: list[str] = []
    a2a_bodies: list[str] = []

    def _on_console(msg) -> None:
        if msg.type != "error":
            return
        text = msg.text
        # Chromium не кладёт URL в текст; реальные 404 ловим в response ниже.
        if "Failed to load resource: the server responded with a status of 404" in text:
            return
        errors.append(f"console.{msg.type}: {text}")

    def _record_embed_request(req) -> None:
        if "/static/core/assets/" in req.url:
            static_urls.append(req.url)
        if "/api/v1/embed/" in req.url or req.url.endswith("/api/flow-ui-token"):
            network_events.append(f"request {req.method} {req.url}")
        if "/api/v1/embed/" in req.url and req.method == "POST":
            body = req.post_data
            if isinstance(body, str) and body != "":
                a2a_bodies.append(body)

    def _record_embed_response(resp) -> None:
        if resp.status == 404 and not _is_benign_embed_host_404(resp.url):
            errors.append(f"http.404: {resp.url}")
        if "/api/v1/embed/" in resp.url or resp.url.endswith("/api/flow-ui-token"):
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
    return errors, network_events, static_urls, a2a_bodies


async def _wait_flow_ui_embed(page: Page, errors: list[str], network_events: list[str]) -> None:
    try:
        await page.wait_for_function(
            "typeof window.linnexFlowUI !== 'undefined' && window.linnexFlowUI && window.linnexFlowUI.element",
            timeout=8_000,
        )
        await page.locator("flow-ui-drawer, flow-ui-page-host").first.wait_for(
            state="attached",
            timeout=5_000,
        )
    except Exception as exc:
        raise AssertionError(
            "linnexFlowUI не смонтировался\n"
            f"errors:\n{chr(10).join(errors) or '<empty>'}\n\n"
            f"network:\n{chr(10).join(network_events) or '<empty>'}"
        ) from exc


def _assert_chrome_static_from_platform(
    static_urls: list[str],
    *,
    frontend_origin: str,
    host_origin: str,
) -> None:
    chrome = [url for url in static_urls if "/static/core/assets/" in url]
    assert chrome, "embed chrome должен грузить иконки или лого с platform-ui-origin"
    platform = frontend_origin.rstrip("/")
    host = host_origin.rstrip("/")
    for url in chrome:
        assert url.startswith(f"{platform}/static/core/"), url
        assert not url.startswith(f"{host}/static/core/"), url


async def _assert_linnex_flow_ui_host_api(page: Page) -> None:
    state = await page.evaluate(
        """async () => {
            const api = window.linnexFlowUI;
            const host = api.element;
            if (host.updateComplete) {
                await host.updateComplete;
            }
            api.setTheme('light');
            api.setMetadataHooks(() => ({ page_url: 'https://shop.example' }));
            let themeThrew = false;
            try {
                api.setTheme('neon');
            } catch (_error) {
                themeThrew = true;
            }
            return {
                embedId: api.embedId,
                presentation: api.presentation,
                theme: host.config.theme,
                hooksOk: typeof host.config.getExtraMetadataVariables === 'function',
                themeThrew,
            };
        }"""
    )
    assert state["presentation"] == "drawer"
    assert state["theme"] == "light"
    assert state["hooksOk"] is True
    assert state["themeThrew"] is True


async def _dispatch_toggle(page: Page, event_name: str, *, open_panel: bool) -> None:
    await page.evaluate(
        """({ eventName, openPanel }) => {
            window.dispatchEvent(new CustomEvent(eventName, { detail: { open: openPanel } }));
        }""",
        {"eventName": event_name, "openPanel": open_panel},
    )


async def _exercise_all_host_api(
    page: Page,
    *,
    expected_embed_id: str,
    presentation: str,
) -> None:
    state = await page.evaluate(
        """async ({ expectedEmbedId, presentation }) => {
            const api = window.linnexFlowUI;
            const host = api.element;
            if (host.updateComplete) {
                await host.updateComplete;
            }
            const flowUi = host.shadowRoot.querySelector('platform-flow-ui');
            const threw = (fn) => {
                try {
                    fn();
                    return false;
                } catch (_error) {
                    return true;
                }
            };
            const snippet = {
                embedId: api.embedId,
                presentation: api.presentation,
                theme: flowUi.theme,
                locale: flowUi.locale,
                credentials: flowUi.credentials,
                companyId: flowUi.getAttribute('company-id'),
                voiceBaseUrl: flowUi.getAttribute('voice-base-url'),
                platformUiOrigin: flowUi.getAttribute('platform-ui-origin'),
                position: host.getAttribute('data-embed-position'),
            };
            api.setTheme('dark');
            const themeDark = flowUi.theme;
            api.setTheme('auto');
            const themeAuto = flowUi.theme;
            api.setTheme('light');
            const themeLight = flowUi.theme;
            const themeThrew = threw(() => api.setTheme('neon'));
            api.setLocale('ru');
            const localeRu = flowUi.locale;
            api.setLocale('en');
            const localeEn = flowUi.locale;
            const localeThrew = threw(() => api.setLocale('de'));
            api.setAssistantTitle('Shop support');
            const title = flowUi.assistantTitle;
            const titleThrew = threw(() => api.setAssistantTitle(''));
            let launcherOn = null;
            let launcherOff = null;
            let launcherThrew = null;
            let launcherPageThrew = null;
            if (presentation === 'drawer') {
                api.setLauncherVisible(true);
                launcherOn = host.config.showLauncher;
                api.setLauncherVisible(false);
                launcherOff = host.config.showLauncher;
                launcherThrew = threw(() => api.setLauncherVisible('no'));
            } else {
                launcherPageThrew = threw(() => api.setLauncherVisible(true));
            }
            api.setToggleEventName('site-chat-open');
            const toggleName = host.config.toggleEventName;
            const toggleThrew = threw(() => api.setToggleEventName(''));
            window.__embedAuthCalls = 0;
            const previousAuth = host.config.getRequestHeaders;
            api.setAuthProvider(() => {
                window.__embedAuthCalls += 1;
                return previousAuth();
            });
            const authThrew = threw(() => api.setAuthProvider(null));
            api.setMetadataHooks(() => ({
                page_url: 'https://shop.example/cart',
                cart_id: 'c1',
            }));
            const metaThrew = threw(() => api.setMetadataHooks(null));
            if (host.updateComplete) {
                await host.updateComplete;
            }
            return {
                snippet,
                expectedEmbedId,
                themeDark,
                themeAuto,
                themeLight,
                themeThrew,
                localeRu,
                localeEn,
                localeThrew,
                title,
                titleThrew,
                launcherOn,
                launcherOff,
                launcherThrew,
                launcherPageThrew,
                toggleName,
                toggleThrew,
                authThrew,
                metaThrew,
            };
        }""",
        {"expectedEmbedId": expected_embed_id, "presentation": presentation},
    )
    assert state["snippet"]["embedId"] == expected_embed_id
    assert state["snippet"]["presentation"] == presentation
    assert state["themeDark"] == "dark"
    assert state["themeAuto"] == "auto"
    assert state["themeLight"] == "light"
    assert state["themeThrew"] is True
    assert state["localeRu"] == "ru"
    assert state["localeEn"] == "en"
    assert state["localeThrew"] is True
    assert state["title"] == "Shop support"
    assert state["titleThrew"] is True
    if presentation == "drawer":
        assert state["launcherOn"] is True
        assert state["launcherOff"] is False
        assert state["launcherThrew"] is True
        assert state["snippet"]["position"] == "bottom-left"
    else:
        assert state["launcherPageThrew"] is True
    assert state["toggleName"] == "site-chat-open"
    assert state["toggleThrew"] is True
    assert state["authThrew"] is True
    assert state["metaThrew"] is True


def _assert_a2a_variables(a2a_bodies: list[str], *, page_url: str, cart_id: str) -> None:
    assert a2a_bodies, "embed должен отправить A2A POST"
    matched: dict[str, object] | None = None
    for raw in a2a_bodies:
        payload = json.loads(raw)
        variables = payload.get("params", {}).get("metadata", {}).get("variables")
        if isinstance(variables, dict) and variables.get("page_url") == page_url:
            matched = variables
            break
    assert matched is not None, f"metadata.variables не найдены в A2A: {a2a_bodies}"
    assert matched["cart_id"] == cart_id


async def _send_embed_message(page: Page, user_line: str, network_events: list[str], errors: list[str]) -> None:
    root = page.locator(
        "flow-ui-drawer platform-flow-ui, flow-ui-page-host platform-flow-ui, platform-flow-ui"
    ).first
    textarea = root.locator('textarea[data-canon="composer"]').first
    await expect(textarea).to_be_visible(timeout=5_000)
    await textarea.fill(user_line)
    send_btn = root.get_by_role("button", name=re.compile(r"^(Send|Отправить)$")).first
    await expect(send_btn).to_be_enabled(timeout=5_000)
    await send_btn.click()
    try:
        await expect(page.get_by_text(f"embed-ok:{user_line}", exact=True)).to_be_visible(timeout=8_000)
    except AssertionError as exc:
        root_text = await root.inner_text(timeout=2_000)
        raise AssertionError(
            "embed браузер: не получен ожидаемый A2A ответ\n"
            f"root_text:\n{root_text}\n\n"
            f"network:\n{chr(10).join(network_events) or '<empty>'}\n\n"
            f"errors:\n{chr(10).join(errors) or '<empty>'}"
        ) from exc


@pytest.mark.timeout(15)
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
    page.set_default_timeout(8_000)
    auth_headers, flow_id, company_id, _user_part = embed_test_auth
    user_line = f"browser-embed-msg-{unique_id}"

    frontend_origin = _frontend_api_origin(frontend_ui).rstrip("/")
    flows_public_base = _flows_api_origin(flows_ui).rstrip("/")
    script_src = f"{frontend_origin}/static/core/lib/embed-flow-ui/flow-ui-embed-autoload.js"
    flows_base = f"{flows_public_base}/flows"

    embed_id: str | None = None
    errors, network_events, static_urls, _a2a_bodies = await _attach_embed_page_diagnostics(page)

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
            await page.goto(f"{host_origin}/", wait_until="domcontentloaded", timeout=8_000)
            await _wait_flow_ui_embed(page, errors, network_events)
            await _assert_linnex_flow_ui_host_api(page)
            await expect(page.locator("flow-ui-drawer")).to_be_attached(timeout=5_000)
            fab = page.locator("flow-ui-drawer").locator("button.launcher, button.fab").first
            await expect(fab).to_be_visible(timeout=5_000)
            await fab.click()
            _assert_chrome_static_from_platform(
                static_urls,
                frontend_origin=frontend_origin,
                host_origin=host_origin,
            )
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
@pytest.mark.timeout(15)
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
    page.set_default_timeout(8_000)
    auth_headers, flow_id, company_id, _user_part = embed_test_auth
    user_line = f"embed-site-{unique_id}"

    frontend_origin = _frontend_api_origin(frontend_ui).rstrip("/")
    flows_public_base = _flows_api_origin(flows_ui).rstrip("/")
    script_src = f"{frontend_origin}/static/core/lib/embed-flow-ui/flow-ui-embed-autoload.js"
    flows_base = f"{flows_public_base}/flows"

    embed_id: str | None = None
    errors, network_events, static_urls, _a2a_bodies = await _attach_embed_page_diagnostics(page)
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
            await page.goto(f"{host_origin}/", wait_until="domcontentloaded", timeout=8_000)
            await _wait_flow_ui_embed(page, errors, network_events)
            await expect(page.locator("flow-ui-drawer")).to_be_attached(timeout=5_000)
            fab = page.locator("flow-ui-drawer").locator("button.launcher, button.fab").first
            await expect(fab).to_be_visible(timeout=5_000)
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
            reply = page.locator("flow-ui-drawer").get_by_text(
                re.compile(rf"embed-ok:{re.escape(user_line)}", re.I)
            ).first
            await expect(reply).to_be_visible(timeout=8_000)
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


@pytest.mark.timeout(15)
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
    page.set_default_timeout(8_000)
    auth_headers, flow_id, company_id, _user_part = embed_test_auth
    user_line = f"browser-embed-toggle-{unique_id}"

    frontend_origin = _frontend_api_origin(frontend_ui).rstrip("/")
    flows_public_base = _flows_api_origin(flows_ui).rstrip("/")
    script_src = f"{frontend_origin}/static/core/lib/embed-flow-ui/flow-ui-embed-autoload.js"
    flows_base = f"{flows_public_base}/flows"

    embed_id: str | None = None
    errors, network_events, static_urls, _a2a_bodies = await _attach_embed_page_diagnostics(page)

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
            await page.goto(f"{host_origin}/", wait_until="domcontentloaded", timeout=8_000)
            await _wait_flow_ui_embed(page, errors, network_events)
            fab = page.locator("flow-ui-drawer").locator("button.launcher, button.fab")
            await expect(fab).to_have_count(0, timeout=5_000)
            await page.evaluate(
                """() => {
                    window.dispatchEvent(
                        new CustomEvent('linnex-flow-ui-toggle', { detail: { open: true } }),
                    );
                }"""
            )
            await _send_embed_message(page, user_line, network_events, errors)
            _assert_chrome_static_from_platform(
                static_urls,
                frontend_origin=frontend_origin,
                host_origin=host_origin,
            )
            if errors:
                pytest.fail("embed toggle: ошибки страницы/консоли:\n" + "\n".join(errors))
    finally:
        if embed_id is not None:
            await _delete_embed_config(frontend_origin, auth_headers, embed_id)


@pytest.mark.timeout(15)
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
    page.set_default_timeout(8_000)
    auth_headers, flow_id, company_id, _user_part = embed_test_auth
    user_line = f"browser-embed-proxy-{unique_id}"

    frontend_origin = _frontend_api_origin(frontend_ui).rstrip("/")
    flows_public_base = _flows_api_origin(flows_ui).rstrip("/")
    script_src = f"{frontend_origin}/static/core/lib/embed-flow-ui/flow-ui-embed-autoload.js"
    flows_base = f"{flows_public_base}/flows"

    embed_id = await _create_embed_config(
        frontend_origin,
        auth_headers,
        flow_id=flow_id,
        unique_id=f"proxy-{unique_id}",
        show_launcher=True,
    )
    errors, network_events, static_urls, _a2a_bodies = await _attach_embed_page_diagnostics(page)

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
            await page.goto(f"{host_origin}/", wait_until="domcontentloaded", timeout=8_000)
            await _wait_flow_ui_embed(page, errors, network_events)
            fab = page.locator("flow-ui-drawer").locator("button.launcher, button.fab").first
            await expect(fab).to_be_visible(timeout=5_000)
            await fab.click()
            await _send_embed_message(page, user_line, network_events, errors)
            token_requests = [line for line in network_events if "/api/flow-ui-token" in line]
            assert token_requests, "autoload должен запросить /api/flow-ui-token у mock host"
            if errors:
                pytest.fail("embed proxy S2S: ошибки страницы/консоли:\n" + "\n".join(errors))
    finally:
        await _delete_embed_config(frontend_origin, auth_headers, embed_id)


@pytest.mark.timeout(30)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_embed_site_all_live_attrs_host_api_and_message(
    page: Page,
    embed_browser_http_stack_ready,
    taskiq_worker,
    frontend_ui: AppUI,
    flows_ui: AppUI,
    embed_test_auth,
    unique_id: str,
) -> None:
    _ = embed_browser_http_stack_ready, taskiq_worker
    page.set_default_timeout(8_000)
    auth_headers, flow_id, company_id, _user_part = embed_test_auth
    user_line = f"embed-matrix-{unique_id}"
    frontend_origin = _frontend_api_origin(frontend_ui).rstrip("/")
    flows_base = f"{_flows_api_origin(flows_ui).rstrip('/')}/flows"
    script_src = f"{frontend_origin}/static/core/lib/embed-flow-ui/flow-ui-embed-autoload.js"
    toggle_name = "shop-open-chat"

    errors, network_events, static_urls, a2a_bodies = await _attach_embed_page_diagnostics(page)
    embed_id = await _create_embed_config(
        frontend_origin,
        auth_headers,
        flow_id=flow_id,
        unique_id=f"matrix-{unique_id}",
        show_launcher=False,
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
        token_payload = {"token": mint.json()["token"]}

    page_html = _build_embed_page_html(
        script_src=script_src,
        embed_id=embed_id,
        flows_base=flows_base,
        frontend_origin=frontend_origin,
        company_id=company_id,
        show_launcher=False,
        presentation="drawer",
        position="bottom-left",
        theme="light",
        locale="en",
        use_credentials=False,
        toggle_event_name=toggle_name,
    )
    try:
        with _external_embed_origin(html_page_utf8=page_html, token_payload=token_payload) as host_origin:
            await page.goto(f"{host_origin}/", wait_until="domcontentloaded", timeout=8_000)
            await _wait_flow_ui_embed(page, errors, network_events)
            snippet = await page.evaluate(
                """() => {
                    const api = window.linnexFlowUI;
                    const host = api.element;
                    const flowUi = host.shadowRoot.querySelector('platform-flow-ui');
                    return {
                        embedId: api.embedId,
                        presentation: api.presentation,
                        theme: flowUi.theme,
                        locale: flowUi.locale,
                        credentials: flowUi.credentials,
                        companyId: flowUi.getAttribute('company-id'),
                        voiceBaseUrl: flowUi.getAttribute('voice-base-url'),
                        platformUiOrigin: flowUi.getAttribute('platform-ui-origin'),
                        position: host.getAttribute('data-embed-position'),
                        launcherCount: host.shadowRoot.querySelectorAll('button.launcher').length,
                    };
                }"""
            )
            assert snippet["embedId"] == embed_id
            assert snippet["presentation"] == "drawer"
            assert snippet["theme"] == "light"
            assert snippet["locale"] == "en"
            assert snippet["credentials"] == "omit"
            assert snippet["companyId"] == company_id
            assert snippet["voiceBaseUrl"] == f"{frontend_origin}/voice"
            assert snippet["platformUiOrigin"] == frontend_origin
            assert snippet["position"] == "bottom-left"
            assert snippet["launcherCount"] == 0

            await _dispatch_toggle(page, toggle_name, open_panel=True)
            await expect(
                page.locator("platform-flow-ui").get_by_role("textbox").first
            ).to_be_visible(timeout=5_000)
            await expect(
                page.locator("platform-flow-ui").get_by_role(
                    "button", name=re.compile(r"Send")
                ).first
            ).to_be_visible(timeout=5_000)

            await _exercise_all_host_api(page, expected_embed_id=embed_id, presentation="drawer")
            await expect(page.locator("flow-ui-drawer").locator("button.launcher")).to_have_count(0)
            title = await page.evaluate(
                """() => window.linnexFlowUI.element.shadowRoot
                    .querySelector('platform-flow-ui').assistantTitle"""
            )
            assert title == "Shop support"
            await _dispatch_toggle(page, "site-chat-open", open_panel=False)
            await expect(page.locator("flow-ui-drawer[open]")).to_have_count(0)
            await _dispatch_toggle(page, toggle_name, open_panel=True)
            await expect(page.locator("flow-ui-drawer[open]")).to_have_count(0)
            await _dispatch_toggle(page, "site-chat-open", open_panel=True)
            await expect(page.locator("flow-ui-drawer[open]")).to_have_count(1)
            close_btn = page.locator("platform-flow-ui").get_by_role(
                "button", name=re.compile(r"^Close$")
            )
            await expect(close_btn).to_be_visible()
            last_chrome_label = await page.evaluate(
                """() => {
                    const flowUi = window.linnexFlowUI.element.shadowRoot
                        .querySelector('platform-flow-ui');
                    const drawerControls = flowUi.shadowRoot.querySelector('.top-actions').lastElementChild;
                    const last = drawerControls.shadowRoot.querySelector('button:last-of-type');
                    return last.getAttribute('aria-label');
                }"""
            )
            assert last_chrome_label == "Close"
            await close_btn.click()
            await expect(page.locator("flow-ui-drawer[open]")).to_have_count(0)
            await _dispatch_toggle(page, "site-chat-open", open_panel=True)
            await expect(page.locator("flow-ui-drawer[open]")).to_have_count(1)
            await _send_embed_message(page, user_line, network_events, errors)
            auth_calls = await page.evaluate("window.__embedAuthCalls")
            assert auth_calls >= 1
            _assert_a2a_variables(
                a2a_bodies,
                page_url="https://shop.example/cart",
                cart_id="c1",
            )
            _assert_chrome_static_from_platform(
                static_urls,
                frontend_origin=frontend_origin,
                host_origin=host_origin,
            )
            if errors:
                pytest.fail("embed matrix: ошибки страницы/консоли:\n" + "\n".join(errors))
    finally:
        await _delete_embed_config(frontend_origin, auth_headers, embed_id)


@pytest.mark.timeout(20)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_embed_page_presentation_streams_reply(
    page: Page,
    embed_browser_http_stack_ready,
    taskiq_worker,
    frontend_ui: AppUI,
    flows_ui: AppUI,
    embed_test_auth,
    unique_id: str,
) -> None:
    _ = embed_browser_http_stack_ready, taskiq_worker
    page.set_default_timeout(8_000)
    auth_headers, flow_id, company_id, _user_part = embed_test_auth
    user_line = f"embed-page-{unique_id}"
    frontend_origin = _frontend_api_origin(frontend_ui).rstrip("/")
    flows_base = f"{_flows_api_origin(flows_ui).rstrip('/')}/flows"
    script_src = f"{frontend_origin}/static/core/lib/embed-flow-ui/flow-ui-embed-autoload.js"

    errors, network_events, static_urls, a2a_bodies = await _attach_embed_page_diagnostics(page)
    embed_id = await _create_embed_config(
        frontend_origin,
        auth_headers,
        flow_id=flow_id,
        unique_id=f"page-{unique_id}",
        show_launcher=False,
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
        token_payload = {"token": mint.json()["token"]}

    page_html = _build_embed_page_html(
        script_src=script_src,
        embed_id=embed_id,
        flows_base=flows_base,
        frontend_origin=frontend_origin,
        company_id=company_id,
        show_launcher=False,
        presentation="page",
        theme="dark",
        locale="ru",
        use_credentials=True,
    )
    try:
        with _external_embed_origin(html_page_utf8=page_html, token_payload=token_payload) as host_origin:
            await page.goto(f"{host_origin}/", wait_until="domcontentloaded", timeout=8_000)
            await _wait_flow_ui_embed(page, errors, network_events)
            await expect(page.locator("flow-ui-page-host")).to_be_attached(timeout=5_000)
            await expect(page.locator("flow-ui-drawer")).to_have_count(0)
            page_state = await page.evaluate(
                """() => {
                    const api = window.linnexFlowUI;
                    const flowUi = api.element.shadowRoot.querySelector('platform-flow-ui');
                    return {
                        presentation: api.presentation,
                        display: flowUi.getAttribute('display'),
                        credentials: flowUi.credentials,
                        theme: flowUi.theme,
                        locale: flowUi.locale,
                    };
                }"""
            )
            assert page_state["presentation"] == "page"
            assert page_state["display"] == "page"
            assert page_state["credentials"] == "include"
            assert page_state["theme"] == "dark"
            assert page_state["locale"] == "ru"
            await _exercise_all_host_api(page, expected_embed_id=embed_id, presentation="page")
            await expect(page.locator("platform-flow-ui").locator(".brand-label")).to_have_text(
                "Shop support"
            )
            await _send_embed_message(page, user_line, network_events, errors)
            auth_calls = await page.evaluate("window.__embedAuthCalls")
            assert auth_calls >= 1
            _assert_a2a_variables(
                a2a_bodies,
                page_url="https://shop.example/cart",
                cart_id="c1",
            )
            _assert_chrome_static_from_platform(
                static_urls,
                frontend_origin=frontend_origin,
                host_origin=host_origin,
            )
            if errors:
                pytest.fail("embed page: ошибки страницы/консоли:\n" + "\n".join(errors))
    finally:
        await _delete_embed_config(frontend_origin, auth_headers, embed_id)


@pytest.mark.timeout(15)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_embed_missing_token_url_fires_error(
    page: Page,
    embed_browser_http_stack_ready,
    frontend_ui: AppUI,
    flows_ui: AppUI,
    embed_test_auth,
    unique_id: str,
) -> None:
    _ = embed_browser_http_stack_ready
    page.set_default_timeout(8_000)
    auth_headers, flow_id, company_id, _user_part = embed_test_auth
    frontend_origin = _frontend_api_origin(frontend_ui).rstrip("/")
    flows_base = f"{_flows_api_origin(flows_ui).rstrip('/')}/flows"
    script_src = f"{frontend_origin}/static/core/lib/embed-flow-ui/flow-ui-embed-autoload.js"
    errors, network_events, _static_urls, _a2a_bodies = await _attach_embed_page_diagnostics(page)
    embed_id = await _create_embed_config(
        frontend_origin,
        auth_headers,
        flow_id=flow_id,
        unique_id=f"notoken-{unique_id}",
        show_launcher=True,
    )
    page_html = _build_embed_page_html(
        script_src=script_src,
        embed_id=embed_id,
        flows_base=flows_base,
        frontend_origin=frontend_origin,
        company_id=company_id,
        show_launcher=True,
        token_url=None,
    )
    try:
        await page.add_init_script(
            """
            window.__embedErrorMessage = null;
            window.addEventListener('linnex-flow-ui-error', (event) => {
                window.__embedErrorMessage = event.detail.message;
            });
            """
        )
        with _external_embed_origin(html_page_utf8=page_html) as host_origin:
            await page.goto(f"{host_origin}/", wait_until="domcontentloaded", timeout=8_000)
            await page.wait_for_function("window.__embedErrorMessage", timeout=8_000)
            error_message = await page.evaluate("window.__embedErrorMessage")
            assert "data-token-url" in error_message
            assert await page.evaluate("typeof window.linnexFlowUI === 'undefined'")
            _ = errors, network_events
    finally:
        await _delete_embed_config(frontend_origin, auth_headers, embed_id)
