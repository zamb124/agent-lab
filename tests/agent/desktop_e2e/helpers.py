"""Общие prod-path helpers для HumanitecAgent desktop E2E."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from httpx import AsyncClient
from playwright.async_api import Browser, Page, expect

from tests.agent._helpers import AGENT_API_PREFIX, create_pairing_via_http
from tests.agent.desktop_e2e.electron_launcher import HumanitecDesktopProcess

REPO_ROOT = Path(__file__).resolve().parents[3]
BUNDLED_EXTENSIONS_PATH = (
    REPO_ROOT
    / "apps/agent/desktop/vendor/goose/ui/desktop/src/components/settings/extensions/bundled-extensions.json"
)
HUMANITEC_PLATFORM_MCP_DISPLAY_NAME = "Humanitec"
# `BottomMenuExtensionSelection` composer-toolbar кнопка не имеет текста (только
# Puzzle-иконка + счётчик) — единственный надёжный accessible-признак это `title`.
_MANAGE_EXTENSIONS_TITLE_RE = re.compile("manage extensions|управлять расширениями", re.IGNORECASE)
_DESKTOP_WAIT_SECONDS = 10.0
_DESKTOP_WAIT_MS = 10_000
_PRODUCT_NAME_MARKERS = (
    "LinnexAgent",
    "HumanitecAgent",
    "Linnex",
    "Goose",
    "Pair device",
    "Pairing",
)


async def create_pairing_code(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
) -> str:
    body = await create_pairing_via_http(
        agent_frontend_http_client,
        auth_cookie=auth_token,
    )
    pairing_code = body["pairing_code"]
    if not isinstance(pairing_code, str) or len(pairing_code) != 6:
        raise ValueError(f"invalid pairing code: {pairing_code!r}")
    return pairing_code


async def wait_for_humanitec_agent_api(
    browser: Browser,
    *,
    timeout_seconds: float = _DESKTOP_WAIT_SECONDS,
) -> Page:
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        for context in browser.contexts:
            for page in context.pages:
                has_api = await page.evaluate("typeof window.humanitecAgent !== 'undefined'")
                if has_api:
                    return page
        await asyncio.sleep(0.5)
    raise TimeoutError("humanitecAgent preload API not available in desktop window")


async def pair_via_humanitec_agent_api(
    browser: Browser,
    pairing_code: str,
    *,
    timeout_seconds: float = _DESKTOP_WAIT_SECONDS,
) -> Page:
    page = await wait_for_humanitec_agent_api(browser, timeout_seconds=timeout_seconds)
    await page.evaluate(
        "(code) => window.humanitecAgent.pair(code)",
        pairing_code,
    )
    return page


async def pair_desktop_via_deep_link(
    desktop_process: HumanitecDesktopProcess,
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    *,
    page: Page | None = None,
) -> tuple[str, dict[str, str]]:
    if desktop_process.credentials_path.is_file():
        existing = desktop_process.read_credentials()
        device_id = existing.get("device_id")
        if isinstance(device_id, str) and device_id not in ("", "pending"):
            return device_id, existing

    pairing_code = await create_pairing_code(agent_frontend_http_client, auth_token)
    if page is not None:
        # Prod IPC path: register через main process, без кликов по pairing UI.
        has_api = await page.evaluate("typeof window.humanitecAgent?.pair === 'function'")
        if has_api:
            await page.evaluate(
                "(code) => window.humanitecAgent.pair(code)",
                pairing_code,
            )
        else:
            code_input = page.locator("[data-humanitec-pairing-code]")
            if await code_input.count() == 0:
                code_input = page.locator("#pairing-code")
            if await code_input.count() == 0:
                raise RuntimeError("HumanitecAgent pairing UI/API not found on provided page")
            await submit_pairing_code_in_ui(page, pairing_code)
    else:
        desktop_process.open_pairing_ui_deep_link()
        from playwright.async_api import async_playwright

        playwright = await async_playwright().start()
        try:
            browser = await connect_desktop_browser(playwright, desktop_process)
            pairing_page = await find_pairing_page(browser)
            has_api = await pairing_page.evaluate(
                "typeof window.humanitecAgent?.pair === 'function'"
            )
            if has_api:
                await pairing_page.evaluate(
                    "(code) => window.humanitecAgent.pair(code)",
                    pairing_code,
                )
            else:
                await submit_pairing_code_in_ui(pairing_page, pairing_code)
        finally:
            await playwright.stop()
    credentials = desktop_process.wait_for_credentials(timeout_seconds=_DESKTOP_WAIT_SECONDS)
    device_id = credentials["device_id"]
    if device_id == "pending":
        raise ValueError("device remained pending after pairing")
    device_item = await desktop_process.wait_for_tunnel_online(
        agent_frontend_http_client,
        device_id,
    )
    policy = device_item.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("device policy missing after pairing")
    return device_id, credentials


async def wait_for_chat_ready(page: Page, *, timeout_ms: int = _DESKTOP_WAIT_MS) -> None:
    """Ждёт chat composer либо явный LLM setup error (не крутит Configuring вечно)."""
    deadline = asyncio.get_event_loop().time() + (timeout_ms / 1000.0)
    while asyncio.get_event_loop().time() < deadline:
        composer = page.locator("[data-humanitec-chat-composer]")
        if await composer.count() > 0 and await composer.first.is_visible():
            return
        error = page.locator("[data-humanitec-llm-setup-error]")
        if await error.count() > 0:
            message = (await error.first.inner_text()).strip()
            raise RuntimeError(f"HumanitecAgent LLM setup failed: {message}")
        body_text = await page.locator("body").inner_text()
        if "Failed to configure platform LLM" in body_text:
            raise RuntimeError(f"HumanitecAgent LLM setup failed: {body_text[:400]!r}")
        await asyncio.sleep(0.25)
    final_body_text = (await page.locator("body").inner_text())[:400]
    raise TimeoutError(
        "HumanitecAgent chat composer not ready after pairing "
        f"(timeout={timeout_ms}ms); body={final_body_text!r}"
    )


async def ensure_humanitec_paired_and_llm_ready(
    desktop: HumanitecDesktopProcess,
    page: Page,
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
) -> None:
    composer = page.locator("[data-humanitec-chat-composer]")
    if await composer.count() > 0:
        credentials = desktop.read_credentials()
        llm_provider_id = credentials.get("llm_provider_id")
        if llm_provider_id != "humanitec":
            raise ValueError(
                f"HumanitecAgent LLM not configured: llm_provider_id={llm_provider_id!r}"
            )
        return
    await pair_desktop_via_deep_link(
        desktop,
        agent_frontend_http_client,
        auth_token,
        page=page,
    )
    # pair() через IPC не зовёт onPaired у guard — перезагрузка, чтобы refreshStatus
    # увидел credentials и прошёл LLM setup → chat.
    await page.reload(wait_until="domcontentloaded")
    await wait_for_chat_ready(page)
    credentials = desktop.read_credentials()
    llm_provider_id = credentials.get("llm_provider_id")
    if llm_provider_id != "humanitec":
        raise ValueError(
            f"HumanitecAgent LLM autoconfig failed: llm_provider_id={llm_provider_id!r}"
        )


async def submit_pairing_code_in_ui(
    page: Page,
    pairing_code: str,
) -> None:
    code_input = page.locator("[data-humanitec-pairing-code]")
    if await code_input.count() == 0:
        code_input = page.locator("#pairing-code")
    await expect(code_input).to_be_visible(timeout=_DESKTOP_WAIT_MS)
    await code_input.fill(pairing_code)
    submit_button = page.locator("[data-humanitec-pair-submit]")
    if await submit_button.count() == 0:
        submit_button = page.locator("#pair-submit")
    await submit_button.click()


async def find_pairing_page(browser: Browser) -> Page:
    deadline = asyncio.get_event_loop().time() + _DESKTOP_WAIT_SECONDS
    while asyncio.get_event_loop().time() < deadline:
        for context in browser.contexts:
            for page in context.pages:
                if await page.locator("#pairing-code").count() > 0:
                    return page
                if await page.locator("[data-humanitec-pairing-code]").count() > 0:
                    return page
        await asyncio.sleep(0.5)
    raise TimeoutError("HumanitecAgent pairing UI page not found")


async def wait_for_device_offline(
    http_client: AsyncClient,
    device_id: str,
    *,
    timeout_seconds: float = _DESKTOP_WAIT_SECONDS,
) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        response = await http_client.get(f"{AGENT_API_PREFIX}/devices")
        response.raise_for_status()
        items = response.json()["items"]
        matched = next(
            (item for item in items if isinstance(item, dict) and item.get("device_id") == device_id),
            None,
        )
        if matched is not None and matched.get("is_tunnel_online") is False:
            return
        await asyncio.sleep(0.5)
    raise TimeoutError(f"device {device_id!r} did not go offline")


def read_bundled_extensions() -> list[dict[str, object]]:
    if not BUNDLED_EXTENSIONS_PATH.is_file():
        raise FileNotFoundError(f"bundled-extensions.json missing: {BUNDLED_EXTENSIONS_PATH}")
    payload = json.loads(BUNDLED_EXTENSIONS_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("bundled-extensions.json must be list")
    return [item for item in payload if isinstance(item, dict)]


async def connect_desktop_browser(playwright, desktop: HumanitecDesktopProcess) -> Browser:
    return await playwright.chromium.connect_over_cdp(
        f"http://127.0.0.1:{desktop.remote_debugging_port}"
    )


async def find_main_app_page(browser: Browser) -> Page:
    deadline = asyncio.get_event_loop().time() + _DESKTOP_WAIT_SECONDS
    last_snapshot: list[str] = []
    while asyncio.get_event_loop().time() < deadline:
        last_snapshot = []
        for context in browser.contexts:
            for page in context.pages:
                title = await page.title()
                url = page.url
                if await page.locator("#pairing-code").count() > 0:
                    return page
                if await page.locator("[data-humanitec-pairing-code]").count() > 0:
                    return page
                if await page.locator("[data-humanitec-chat-composer]").count() > 0:
                    return page
                body_text = await page.locator("body").inner_text()
                last_snapshot.append(f"title={title!r} url={url!r} body={body_text[:240]!r}")
                if "Configuring Platform Brain" in body_text:
                    continue
                if await page.locator("textarea").count() > 0:
                    return page
                if any(marker in body_text for marker in _PRODUCT_NAME_MARKERS):
                    return page
                if await page.evaluate("typeof window.humanitecAgent !== 'undefined'"):
                    return page
        await asyncio.sleep(0.5)
    raise TimeoutError(
        "HumanitecAgent/LinnexAgent main window not found within "
        f"{_DESKTOP_WAIT_SECONDS}s; pages={last_snapshot!r}"
    )


async def open_ready_main_page(browser: Browser) -> Page:
    """Находит главное окно и доводит его до chat-ready после IPC-pairing.

    pair() через IPC не зовёт onPaired у guard — перезагрузка, чтобы refreshStatus
    увидел credentials, прошёл LLM setup и синхронизировал расширения → chat.
    """
    page = await find_main_app_page(browser)
    composer = page.locator("[data-humanitec-chat-composer]")
    if not (await composer.count() > 0 and await composer.first.is_visible()):
        await page.reload(wait_until="domcontentloaded")
    await wait_for_chat_ready(page)
    return page


async def open_settings_extensions(page: Page) -> None:
    await page.evaluate("window.location.hash = '/extensions'")
    await page.wait_for_timeout(2000)


async def assert_platform_mcp_first_in_settings(page: Page) -> None:
    await open_settings_extensions(page)
    body_text = await page.locator("body").inner_text()
    platform_index = body_text.find(HUMANITEC_PLATFORM_MCP_DISPLAY_NAME)
    if platform_index < 0:
        raise AssertionError(
            f"{HUMANITEC_PLATFORM_MCP_DISPLAY_NAME!r} not found in settings body"
        )
    for other_label in ("Developer", "Computer Controller", "Memory"):
        other_index = body_text.find(other_label)
        if other_index >= 0 and other_index < platform_index:
            raise AssertionError(
                f"extension {other_label!r} appears before platform MCP in settings"
            )


async def open_chat_mcp_picker(page: Page) -> None:
    await page.evaluate("window.location.hash = '/'")
    await page.wait_for_timeout(2000)
    # `BottomMenuExtensionSelection` toolbar button — иконка + счётчик, без текста;
    # приоритет перед `[data-humanitec-mcp-picker]`, т.к. sidebar nav-пункт
    # "Extensions" использует ту же Puzzle-иконку и может получить тот же атрибут.
    manage_extensions_button = page.get_by_title(_MANAGE_EXTENSIONS_TITLE_RE)
    if await manage_extensions_button.count() > 0:
        await manage_extensions_button.first.click()
        await page.wait_for_timeout(1000)
        return
    mcp_button = page.locator("[data-humanitec-mcp-picker]")
    if await mcp_button.count() > 0:
        await mcp_button.first.click()
        await page.wait_for_timeout(1000)
        return
    raise AssertionError("MCP/extensions picker control not found in chat UI")


async def assert_platform_mcp_first_in_chat_picker(page: Page) -> None:
    await open_chat_mcp_picker(page)
    body_text = await page.locator("body").inner_text()
    platform_index = body_text.find(HUMANITEC_PLATFORM_MCP_DISPLAY_NAME)
    if platform_index < 0:
        raise AssertionError(
            f"{HUMANITEC_PLATFORM_MCP_DISPLAY_NAME!r} not visible in chat MCP picker"
        )


async def assert_humanitec_preload_api(page: Page) -> None:
    has_api = await page.evaluate("typeof window.humanitecAgent !== 'undefined'")
    if not has_api:
        raise AssertionError("window.humanitecAgent preload API missing")
    has_resync = await page.evaluate(
        "typeof window.humanitecAgent.resyncExtensions === 'function'"
    )
    if not has_resync:
        raise AssertionError("humanitecAgent.resyncExtensions missing")
    has_resolve = await page.evaluate(
        "typeof window.humanitecAgent.resolveEnvTemplates === 'function'"
    )
    if not has_resolve:
        raise AssertionError("humanitecAgent.resolveEnvTemplates missing")


async def send_chat_message(page: Page, message: str) -> None:
    composer = page.locator("[data-humanitec-chat-composer]")
    if await composer.count() == 0:
        composer = page.locator("textarea").first
    await expect(composer).to_be_visible(timeout=_DESKTOP_WAIT_MS)
    await composer.fill(message)
    send_button = page.locator("[data-humanitec-chat-send]")
    if await send_button.count() == 0:
        send_button = page.get_by_role("button", name="Send")
    if await send_button.count() > 0:
        await send_button.first.click()
        return
    await composer.press("Enter")
