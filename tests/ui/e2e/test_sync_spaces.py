"""E2E: редактирование пространства Sync."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="sync",
    tag="spaces",
    title="Sync: редактирование пространства",
    description=(
        "Пользователь открывает настройки существующего пространства через иконку шестерёнки, "
        "меняет название и сохраняет."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_user_edits_space_name(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    space_name = f"E2E space edit {unique_id}"
    updated_suffix = f" обновлено {unique_id}"

    await sync_ui.open(ui_page_system)
    await sync_ui.expect_shell(ui_page_system)
    await scenario.step("Sync открыт", ui_page_system)

    await ui_page_system.get_by_role("button", name="Создать пространство").click()
    create_modal = ui_page_system.locator("space-settings-modal")
    await expect(create_modal).to_be_visible()
    inputs_create = create_modal.locator('input.input:not([type="file"])')
    await inputs_create.nth(0).fill(space_name)
    await create_modal.get_by_role("button", name="Создать", exact=True).click()
    await expect(
        ui_page_system.locator("button.space-chip-main").filter(has_text=space_name)
    ).to_be_visible(timeout=30_000)
    await scenario.step("Создано пространство для последующего редактирования", ui_page_system)

    chip = ui_page_system.locator(".space-chip").filter(
        has=ui_page_system.locator("button.space-chip-main").filter(has_text=space_name)
    )
    await chip.get_by_role("button", name="Настройки пространства").click()
    edit_modal = ui_page_system.locator("space-settings-modal")
    await expect(edit_modal).to_be_visible()
    await expect(ui_page_system.get_by_role("heading", name="Настройки пространства")).to_be_visible()
    await scenario.step("Открыты настройки пространства", ui_page_system)

    name_input = edit_modal.locator('input.input:not([type="file"])').first
    await name_input.fill(space_name + updated_suffix)
    await edit_modal.get_by_role("button", name="Сохранить", exact=True).click()
    await expect(
        ui_page_system.locator("button.space-chip-main").filter(
            has_text=space_name + updated_suffix
        )
    ).to_be_visible(timeout=30_000)
    await scenario.step("Название пространства обновлено в списке", ui_page_system)
