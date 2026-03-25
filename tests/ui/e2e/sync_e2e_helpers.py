"""Общие локаторы для E2E Sync (сайдбар vs шапка чата)."""

from __future__ import annotations

import httpx
from playwright.async_api import Locator, Page


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
    if not isinstance(payload, list):
        raise AssertionError("GET /channels/ должен вернуть список.")
    for ch in payload:
        if isinstance(ch, dict) and ch.get("name") == channel_name and isinstance(ch.get("id"), str):
            return ch["id"]
    raise AssertionError(f"Канал с именем {channel_name!r} не найден в API.")


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
        messages = r.json()
    if not isinstance(messages, list):
        raise AssertionError("GET messages должен вернуть список.")
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
