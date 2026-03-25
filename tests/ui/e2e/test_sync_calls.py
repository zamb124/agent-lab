"""E2E: звонок в канале и страница входа по ссылке."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import sync_sidebar_channel_nav
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="sync",
    tag="calls",
    title="Sync: старт звонка из шапки канала",
    description=(
        "В topic-канале пользователь нажимает «Звонок в этом канале»; после ответа сервера "
        "отображается оверлей звонка (атрибут data-call-active на sync-app)."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_user_starts_channel_call_overlay(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    space_name = f"E2E call space {unique_id}"
    channel_name = f"Канал звонка {unique_id}"

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

    await sync_sidebar_channel_nav(ui_page_system, channel_name).click()
    await expect(ui_page_system.locator("chat-view")).to_be_visible()
    await scenario.step("Открыт topic-канал", ui_page_system)

    await ui_page_system.get_by_role("button", name="Звонок в этом канале").click()
    await expect(ui_page_system.locator("sync-app")).to_have_attribute("data-call-active", "", timeout=90_000)
    await expect(ui_page_system.locator("call-overlay")).to_be_visible(timeout=15_000)
    await scenario.step("Отображается оверлей звонка", ui_page_system)


@pytest.mark.scenario(
    service="sync",
    tag="calls",
    title="Sync: страница входа по недействительной ссылке",
    description="Публичная страница /sync/join/{token} показывает сообщение об ошибке для несуществующего токена.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
async def test_call_join_page_shows_error_for_invalid_token(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    page: Page,
) -> None:
    await page.goto(f"{sync_ui.origin}/sync/join/invalid-token-e2e", wait_until="domcontentloaded")
    await expect(page.get_by_text("Ссылка не найдена или истекла.")).to_be_visible(timeout=30_000)
    await scenario.step("Сообщение об ошибке для неверной ссылки", page)
