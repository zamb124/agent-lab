"""E2E: создание пространства в Sync (название и описание)."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="sync",
    tag="spaces",
    doc_slug="create-space",
    title="Sync: создание пространства",
    description=(
        "Пользователь открывает Sync, нажимает «+» у раздела «Пространства», "
        "вводит название и описание и подтверждает создание."
    ),
    title_en="Sync: creating a space",
    description_en=(
        "The user opens Sync, clicks «+» next to «Spaces», "
        "enters a name and description, and confirms creation."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_user_creates_space_with_name_and_description(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    space_name = f"E2E пространство {unique_id}"
    space_description = f"Описание для автотеста {unique_id}"

    await sync_ui.open(ui_page_system)
    await sync_ui.expect_shell(ui_page_system)
    await scenario.step(
        "Открыт Sync, видна оболочка",
        ui_page_system,
        label_en="Sync is open, shell is visible",
    )

    await ui_page_system.get_by_role("button", name="Создать пространство").click()
    modal = ui_page_system.locator("space-settings-modal")
    await expect(modal).to_be_visible()
    await expect(
        ui_page_system.get_by_role("heading", name="Создать пространство")
    ).to_be_visible()
    await scenario.step(
        "Открыто модальное окно создания пространства",
        ui_page_system,
        label_en="Create space modal is open",
    )

    name_input = modal.locator('label.label:has-text("Название") + input.input')
    description_input = modal.locator('label.label:has-text("Описание") + input.input')
    await expect(name_input).to_have_count(1)
    await expect(description_input).to_have_count(1)
    await name_input.fill(space_name)
    await description_input.fill(space_description)
    await scenario.step(
        "Заполнены название и описание",
        ui_page_system,
        label_en="Name and description filled in",
    )

    await modal.get_by_role("button", name="Создать", exact=True).click()
    await expect(ui_page_system.get_by_role("button", name=space_name)).to_be_visible(
        timeout=30_000
    )
    await scenario.step(
        "Пространство появилось в списке",
        ui_page_system,
        label_en="Space appears in the list",
    )
