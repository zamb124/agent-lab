"""Общие prod-path helpers для HumanitecAgent desktop E2E."""

from __future__ import annotations

import asyncio
import json
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
HUMANITEC_PLATFORM_MCP_DISPLAY_NAME = "Humanitec Platform MCP"


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


async def pair_desktop_via_deep_link(
    desktop_process: HumanitecDesktopProcess,
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    *,
    page: Page | None = None,
) -> tuple[str, dict[str, str]]:
    pairing_code = await create_pairing_code(agent_frontend_http_client, auth_token)
    if page is not None:
        code_input = page.locator("[data-humanitec-pairing-code]")
        if await code_input.count() == 0:
            code_input = page.locator("#pairing-code")
        if await code_input.count() == 0:
            raise RuntimeError("HumanitecAgent pairing UI not found on provided page")
        await submit_pairing_code_in_ui(page, pairing_code)
    else:
        from playwright.async_api import async_playwright

        playwright = await async_playwright().start()
        try:
            browser = await connect_desktop_browser(playwright, desktop_process)
            pairing_page = await find_main_app_page(browser)
            await submit_pairing_code_in_ui(pairing_page, pairing_code)
        finally:
            await playwright.stop()
    credentials = desktop_process.wait_for_credentials(timeout_seconds=120.0)
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
    await page.wait_for_selector("[data-humanitec-chat-composer]", timeout=120_000)
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
    await expect(code_input).to_be_visible(timeout=30_000)
    await code_input.fill(pairing_code)
    submit_button = page.locator("[data-humanitec-pair-submit]")
    if await submit_button.count() == 0:
        submit_button = page.locator("#pair-submit")
    await submit_button.click()


async def find_pairing_page(browser: Browser) -> Page:
    deadline = asyncio.get_event_loop().time() + 60.0
    while asyncio.get_event_loop().time() < deadline:
        for context in browser.contexts:
            for page in context.pages:
                if await page.locator("#pairing-code").count() > 0:
                    return page
        await asyncio.sleep(0.5)
    raise TimeoutError("HumanitecAgent pairing UI page not found")


async def wait_for_device_offline(
    http_client: AsyncClient,
    device_id: str,
    *,
    timeout_seconds: float = 30.0,
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
    deadline = asyncio.get_event_loop().time() + 120.0
    while asyncio.get_event_loop().time() < deadline:
        for context in browser.contexts:
            for page in context.pages:
                if await page.locator("#pairing-code").count() > 0:
                    return page
                if await page.locator("[data-humanitec-pairing-code]").count() > 0:
                    return page
                if await page.locator("[data-humanitec-chat-composer]").count() > 0:
                    return page
                if await page.locator("textarea").count() > 0:
                    return page
                body_text = await page.locator("body").inner_text()
                if "HumanitecAgent" in body_text or "Pair device" in body_text:
                    return page
        await asyncio.sleep(0.5)
    raise TimeoutError("HumanitecAgent main window not found")


async def open_settings_extensions(page: Page) -> None:
    await page.evaluate("window.location.hash = '/settings'")
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
    mcp_button = page.locator("[data-humanitec-mcp-picker]")
    if await mcp_button.count() > 0:
        await mcp_button.first.click()
        await page.wait_for_timeout(1000)
        return
    mcp_button = page.get_by_role("button", name="MCP")
    if await mcp_button.count() > 0:
        await mcp_button.first.click()
        await page.wait_for_timeout(1000)
        return
    extensions_button = page.get_by_text("Extensions", exact=False)
    if await extensions_button.count() > 0:
        await extensions_button.first.click()
        await page.wait_for_timeout(1000)
        return
    tools_button = page.get_by_text("Tools", exact=False)
    if await tools_button.count() > 0:
        await tools_button.first.click()
        await page.wait_for_timeout(1000)
        return
    raise AssertionError("MCP/extensions/tools picker control not found in chat UI")


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


async def send_chat_message(page: Page, message: str) -> None:
    composer = page.locator("[data-humanitec-chat-composer]")
    if await composer.count() == 0:
        composer = page.locator("textarea").first
    await expect(composer).to_be_visible(timeout=30_000)
    await composer.fill(message)
    send_button = page.locator("[data-humanitec-chat-send]")
    if await send_button.count() == 0:
        send_button = page.get_by_role("button", name="Send")
    if await send_button.count() > 0:
        await send_button.first.click()
        return
    await composer.press("Enter")
