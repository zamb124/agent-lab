"""Общие локаторы для E2E Sync (сайдбар vs шапка чата)."""

from __future__ import annotations

import httpx
from playwright.async_api import Locator, Page, expect


def sync_sidebar_channel_nav(page: Page, channel_name: str) -> Locator:
    """Кнопка выбора канала в сайдбаре (не шапка chat-view)."""
    return page.locator("sync-sidebar").locator("sync-channel-row").filter(
        has_text=channel_name
    ).locator("button.nav-item")


def sync_sidebar_channel_settings_gear(page: Page, channel_name: str) -> Locator:
    """Кнопка настроек канала в строке сайдбара (рядом с sync-channel-row)."""
    return page.locator("sync-sidebar").locator(".nav-row-wrap").filter(
        has=page.locator("sync-channel-row").filter(has_text=channel_name)
    ).get_by_role("button", name="Настройки канала")


async def sync_e2e_click_create_channel(page: Page) -> None:
    """Открывает модалку создания канала: primary на shell (`sync-channel-picker`) или «+» в секции чатов сайдбара."""
    picker_ru = page.locator("sync-channel-picker").get_by_role("button", name="Создать канал")
    picker_en = page.locator("sync-channel-picker").get_by_role("button", name="Create channel")
    from_picker = picker_ru.or_(picker_en)
    from_sidebar = page.locator("sync-sidebar .section-action-btn").first
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
    await ch_modal.locator("input.form-input").first.fill(channel_name)
    submit = ch_modal.get_by_role("button", name="Создать", exact=True).or_(
        ch_modal.get_by_role("button", name="Create", exact=True)
    )
    await submit.click()
    await expect(sync_sidebar_channel_nav(page, channel_name)).to_be_visible(timeout=30_000)
    await sync_sidebar_channel_nav(page, channel_name).click()
    await expect(page.locator("chat-view")).to_be_visible()
    return channel_name


async def sync_e2e_create_topic_channel_in_current_space(page: Page, unique_id: str, *, channel_prefix: str) -> str:
    """Второй и следующие каналы в том же UI (кнопка «+» в секции чатов)."""
    channel_name = f"{channel_prefix} {unique_id}"
    await sync_e2e_click_create_channel(page)
    ch_modal = page.locator("sync-channel-create-modal")
    await expect(ch_modal).to_be_visible()
    await ch_modal.locator("input.form-input").first.fill(channel_name)
    submit = ch_modal.get_by_role("button", name="Создать", exact=True).or_(
        ch_modal.get_by_role("button", name="Create", exact=True)
    )
    await submit.click()
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
        if isinstance(ch, dict) and ch.get("name") == channel_name and isinstance(ch.get("id"), str):
            return ch["id"]
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
        mid = m.get("id")
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
