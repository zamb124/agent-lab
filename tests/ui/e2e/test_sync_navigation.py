"""E2E: открытие Sync с query channel= в URL."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_e2e_create_topic_channel_and_open,
    sync_e2e_expect_ws_open,
    sync_e2e_open_with_namespace,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="sync",
    tag="navigation",
    doc_slug="channel-from-url-query",
    title="Sync: переход по прямой ссылке на канал",
    description=(
        "После создания канала в UI тест получает id канала через API и открывает "
        "Sync по `/sync/c/{channel_id}` — выбранный канал и чат подгружаются автоматически."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_opens_channel_from_url_query(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    channel_name = f"Канал deep {unique_id}"
    msg_text = f"Проверка deep link {unique_id}"

    await sync_e2e_open_with_namespace(sync_ui, ui_page_system, unique_id, suffix="nav")
    await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Канал deep",
    )

    res = await ui_page_system.request.get(f"{sync_ui.origin}/sync/api/v1/channels/")
    if res.status != 200:
        body = await res.text()
        raise AssertionError(f"Ожидался 200 от списка каналов, получено {res.status}: {body}")
    payload = await res.json()
    if not isinstance(payload, dict) or "items" not in payload:
        raise AssertionError("Ответ /channels/ должен быть OffsetPage с полем items.")
    channel_id = None
    for ch in payload["items"]:
        if not isinstance(ch, dict) or ch.get("name") != channel_name:
            continue
        candidate = ch.get("channel_id") or ch.get("id")
        if isinstance(candidate, str) and candidate:
            channel_id = candidate
            break
    if channel_id is None:
        raise AssertionError(f"Канал {channel_name!r} не найден в ответе API.")

    deep_url = f"{sync_ui.origin}/sync/c/{channel_id}"
    await ui_page_system.goto(deep_url, wait_until="domcontentloaded")
    await sync_ui.expect_shell(ui_page_system)
    await sync_e2e_expect_ws_open(ui_page_system)
    await scenario.step("Повторное открытие Sync по прямой ссылке канала", ui_page_system)

    composer = ui_page_system.locator("sync-message-composer")
    await expect(composer).to_be_visible(timeout=30_000)
    await composer.locator('textarea[data-canon="composer"]').fill(msg_text)
    await composer.locator('button.send').click()
    await expect(
        ui_page_system.locator("sync-message-bubble").get_by_text(msg_text, exact=True)
    ).to_be_visible(timeout=60_000)
    await scenario.step("Сообщение уходит в канал, выбранный из URL", ui_page_system)
