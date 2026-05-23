"""Общие локаторы для E2E Sync (сайдбар vs шапка чата)."""

from __future__ import annotations

import json
import re

import httpx
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator, Page, expect


def _namespace_name(unique_id: str, suffix: str) -> str:
    safe_suffix = suffix.strip("_")
    return f"ns_{unique_id}_{safe_suffix}" if safe_suffix else f"ns_{unique_id}"


async def sync_e2e_seed_namespace(
    unique_id: str,
    *,
    suffix: str = "ui",
    company_id: str = "system",
) -> str:
    """Создаёт платформенный namespace для текущего UI-сценария."""
    from tests.sync.api._helpers import seed_namespace_via_repo

    namespace = _namespace_name(unique_id, suffix)
    return await seed_namespace_via_repo(company_id, namespace)


async def sync_e2e_activate_namespace_for_next_load(
    page: Page,
    namespace: str,
    *,
    company_id: str = "system",
) -> None:
    """Запоминает namespace в localStorage до открытия SPA, как делает CRM/Sync sidebar."""
    company_json = json.dumps(company_id)
    namespace_json = json.dumps(namespace)
    await page.add_init_script(
        f"""
        (() => {{
            const key = 'crm:last-namespace-by-company';
            let map = {{}};
            try {{
                const raw = window.localStorage.getItem(key);
                if (raw) {{
                    const parsed = JSON.parse(raw);
                    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) map = parsed;
                }}
            }} catch {{}}
            map[{company_json}] = {namespace_json};
            window.localStorage.setItem(key, JSON.stringify(map));
        }})();
        """
    )


async def sync_e2e_expect_namespace(page: Page, namespace: str, *, timeout: float = 30_000) -> None:
    field = page.locator("platform-sidebar-namespace-select").first
    await expect(field.locator("platform-field-enum input.field-pill-enum-input")).to_have_value(
        namespace,
        timeout=timeout,
    )


async def sync_e2e_expect_ws_open(page: Page) -> None:
    await page.wait_for_function(
        """() => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.getState !== 'function') return false;
            const state = bus.getState();
            return state?.network?.ws?.status === 'open';
        }""",
        timeout=30_000,
    )


async def sync_e2e_select_namespace(page: Page, namespace: str) -> None:
    for attempt in range(3):
        try:
            field = page.locator("platform-sidebar-namespace-select").first
            input_box = field.locator("platform-field-enum input.field-pill-enum-input")
            await expect(input_box).to_be_visible(timeout=10_000)
            if await input_box.input_value(timeout=2_000) == namespace:
                return
            await input_box.click(timeout=10_000)
            await input_box.fill(namespace, timeout=10_000)
            option = field.get_by_role("option", name=namespace)
            await expect(option).to_be_visible(timeout=10_000)
            await option.click(timeout=10_000)
            await sync_e2e_expect_namespace(page, namespace)
            return
        except PlaywrightError:
            if attempt == 2:
                raise
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(500)


async def sync_e2e_open_with_namespace(
    sync_ui,
    page: Page,
    unique_id: str,
    *,
    suffix: str = "ui",
    company_id: str = "system",
) -> str:
    namespace = await sync_e2e_seed_namespace(unique_id, suffix=suffix, company_id=company_id)
    await sync_e2e_activate_namespace_for_next_load(page, namespace, company_id=company_id)
    await sync_ui.open(page)
    await sync_ui.expect_shell(page)
    await sync_e2e_expect_ws_open(page)
    try:
        await sync_e2e_expect_namespace(page, namespace, timeout=5_000)
        return namespace
    except PlaywrightError:
        pass
    await sync_e2e_select_namespace(page, namespace)
    return namespace


async def sync_e2e_click_platform_button(
    scope: Page | Locator,
    *labels: str,
    timeout: float = 30_000,
) -> None:
    """Кликает по platform-button по видимому тексту slotted label."""
    if not labels:
        raise ValueError("Нужен хотя бы один текст кнопки.")
    exact_labels = "|".join(re.escape(label) for label in labels)
    label_pattern = re.compile(rf"^\s*(?:{exact_labels})\s*$")
    host = scope.locator("platform-button").filter(has_text=label_pattern).first
    await expect(host).to_be_visible(timeout=timeout)
    shadow_button = host.locator("button").first
    await expect(shadow_button).to_be_enabled(timeout=timeout)
    await shadow_button.click(no_wait_after=True)


def sync_sidebar_channel_row(page: Page, channel_name: str) -> Locator:
    """Host-строка канала в сайдбаре."""
    return page.locator("sync-sidebar").locator("sync-channel-row").filter(
        has_text=channel_name
    ).first


def sync_sidebar_channel_nav(page: Page, channel_name: str) -> Locator:
    """Кликабельная область выбора канала в сайдбаре."""
    return sync_sidebar_channel_row(page, channel_name).locator(".row-body").first


def sync_sidebar_channel_settings_gear(page: Page, channel_name: str) -> Locator:
    """Кнопка настроек канала в строке сайдбара."""
    return sync_sidebar_channel_row(page, channel_name).locator("button.gear").first


async def sync_e2e_click_create_channel(page: Page) -> None:
    """Открывает модалку создания канала: primary на shell (`sync-channel-picker`) или «+» в секции чатов сайдбара."""
    picker_ru = page.locator("sync-channel-picker").get_by_role("button", name="Создать канал")
    picker_en = page.locator("sync-channel-picker").get_by_role("button", name="Create channel")
    from_picker = picker_ru.or_(picker_en)
    from_sidebar = page.locator("sync-chat-list .section-action-btn").first
    target = from_picker.or_(from_sidebar)
    await expect(target).to_be_visible(timeout=30_000)
    await target.click()


async def sync_e2e_create_topic_channel_and_open(
    page: Page,
    unique_id: str,
    *,
    channel_prefix: str = "Канал",
) -> str:
    """Создаёт групповой канал и открывает чат. Shell уже должен быть загружен."""
    channel_name = f"{channel_prefix} {unique_id}"
    await sync_e2e_click_create_channel(page)
    ch_modal = page.locator("sync-channel-create-modal")
    await expect(ch_modal).to_be_visible()
    await ch_modal.locator("input.field-pill-input").first.fill(channel_name)
    await sync_e2e_click_platform_button(ch_modal, "Создать", "Create")
    await expect(sync_sidebar_channel_nav(page, channel_name)).to_be_visible(timeout=30_000)
    await sync_sidebar_channel_nav(page, channel_name).click()
    await expect(page.locator("sync-channel-page")).to_be_visible()
    return channel_name


async def sync_e2e_create_topic_channel_in_current_space(page: Page, unique_id: str, *, channel_prefix: str) -> str:
    """Второй и следующие каналы в том же UI (кнопка «+» в секции чатов)."""
    channel_name = f"{channel_prefix} {unique_id}"
    await sync_e2e_click_create_channel(page)
    ch_modal = page.locator("sync-channel-create-modal")
    await expect(ch_modal).to_be_visible()
    await ch_modal.locator("input.field-pill-input").first.fill(channel_name)
    await sync_e2e_click_platform_button(ch_modal, "Создать", "Create")
    await expect(sync_sidebar_channel_nav(page, channel_name)).to_be_visible(timeout=30_000)
    return channel_name


def _sync_client(origin: str, auth_token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=origin,
        cookies={"auth_token": auth_token},
        timeout=60.0,
    )


async def sync_api_channel_id_by_name(origin: str, auth_token: str, channel_name: str) -> str:
    async with _sync_client(origin, auth_token) as client:
        r = await client.get("/sync/api/v1/channels/")
        r.raise_for_status()
        payload = r.json()
    if not isinstance(payload, dict) or "items" not in payload:
        raise AssertionError("GET /channels/ должен вернуть OffsetPage с полем items.")
    for ch in payload["items"]:
        if not isinstance(ch, dict) or ch.get("name") != channel_name:
            continue
        channel_id = ch.get("channel_id") or ch.get("id")
        if isinstance(channel_id, str) and channel_id:
            return channel_id
    raise AssertionError(f"Канал с именем {channel_name!r} не найден в API.")


async def sync_api_add_channel_member(
    origin: str,
    auth_token: str,
    channel_id: str,
    user_id: str,
    role: str = "member",
) -> None:
    async with _sync_client(origin, auth_token) as client:
        r = await client.post(
            f"/sync/api/v1/channels/{channel_id}/members",
            json={"user_id": user_id, "role": role},
        )
        r.raise_for_status()


async def sync_api_post_plain_message(
    origin: str,
    auth_token: str,
    channel_id: str,
    text: str,
) -> None:
    async with _sync_client(origin, auth_token) as client:
        r = await client.post(
            f"/sync/api/v1/channels/{channel_id}/messages",
            json={
                "thread_id": None,
                "parent_message_id": None,
                "contents": [
                    {"type": "text/plain", "data": {"body": text}, "order": 0},
                ],
            },
        )
        r.raise_for_status()


async def sync_api_react_to_message(
    origin: str,
    auth_token: str,
    channel_id: str,
    message_id: str,
    emoji: str,
) -> None:
    async with _sync_client(origin, auth_token) as client:
        r = await client.post(
            f"/sync/api/v1/channels/{channel_id}/messages/{message_id}/react",
            json={"emoji": emoji},
        )
        r.raise_for_status()


async def sync_api_find_message_id_with_text(
    origin: str,
    auth_token: str,
    channel_id: str,
    substring: str,
) -> str:
    async with _sync_client(origin, auth_token) as client:
        r = await client.get(f"/sync/api/v1/channels/{channel_id}/messages")
        r.raise_for_status()
        payload = r.json()
    if not isinstance(payload, dict):
        raise AssertionError("GET messages должен вернуть объект пагинации.")
    messages = payload.get("items")
    if not isinstance(messages, list):
        raise AssertionError("GET messages должен вернуть массив в поле items.")
    for m in messages:
        if not isinstance(m, dict):
            continue
        mid = m.get("message_id") if isinstance(m.get("message_id"), str) else m.get("id")
        contents = m.get("contents")
        if not isinstance(mid, str) or not isinstance(contents, list):
            continue
        for block in contents:
            if not isinstance(block, dict):
                continue
            data = block.get("data")
            if isinstance(data, dict) and substring in str(data.get("body", "")):
                return mid
    raise AssertionError(f"Сообщение с текстом, содержащим {substring!r}, не найдено.")
