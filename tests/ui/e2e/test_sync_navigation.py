"""E2E: открытие Sync с query channel= в URL."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import sync_sidebar_channel_nav
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="sync",
    tag="navigation",
    doc_slug="channel-from-url-query",
    title="Sync: переход по ссылке с параметром channel",
    description=(
        "После создания канала в UI тест получает id канала через API и открывает "
        "Sync с `?channel=` — выбранный канал и чат подгружаются автоматически."
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
    space_name = f"E2E nav space {unique_id}"
    channel_name = f"Канал deep {unique_id}"
    msg_text = f"Проверка deep link {unique_id}"

    await sync_ui.open(ui_page_system)
    await sync_ui.expect_shell(ui_page_system)

    await ui_page_system.get_by_role("button", name="Создать пространство").click()
    sm = ui_page_system.locator("space-settings-modal")
    await expect(sm).to_be_visible()
    ins = sm.locator('input.input:not([type="file"])')
    await ins.nth(0).fill(space_name)
    await sm.get_by_role("button", name="Создать", exact=True).click()
    await expect(ui_page_system.get_by_role("button", name=space_name)).to_be_visible(
        timeout=30_000
    )

    await ui_page_system.get_by_role("button", name="Создать канал").click()
    ch_modal = ui_page_system.locator("channel-settings-modal")
    await expect(ch_modal).to_be_visible()
    await ch_modal.get_by_placeholder("Название канала").fill(channel_name)
    await ch_modal.get_by_role("button", name="Создать", exact=True).click()
    await expect(sync_sidebar_channel_nav(ui_page_system, channel_name)).to_be_visible(
        timeout=30_000
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
        if isinstance(ch, dict) and ch.get("name") == channel_name and isinstance(ch.get("id"), str):
            channel_id = ch["id"]
            break
    if channel_id is None:
        raise AssertionError(f"Канал {channel_name!r} не найден в ответе API.")

    deep_url = f"{sync_ui.spa_url()}?channel={channel_id}"
    await ui_page_system.goto(deep_url, wait_until="domcontentloaded")
    await sync_ui.expect_shell(ui_page_system)
    await expect(ui_page_system.locator(".ws-badge.open")).to_be_visible(timeout=30_000)
    await scenario.step("Повторное открытие Sync с ?channel=", ui_page_system)

    composer = ui_page_system.locator("message-composer")
    await expect(composer).to_be_visible(timeout=30_000)
    await composer.locator("textarea[placeholder='Сообщение...']").fill(msg_text)
    await composer.locator('button.send[title="Отправить"]').click()
    await expect(
        ui_page_system.locator("message-bubble").get_by_text(msg_text, exact=True)
    ).to_be_visible(timeout=60_000)
    await scenario.step("Сообщение уходит в канал, выбранный из URL", ui_page_system)
