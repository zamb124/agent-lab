"""E2E: настройки Sync defaults (company workspace ``default``)."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_e2e_click_platform_button,
    sync_e2e_open_sync_defaults,
    sync_e2e_open_with_namespace,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="sync",
    tag="spaces",
    doc_slug="edit-space-name",
    title="Sync: настройки транскрипции",
    description=(
        "Пользователь открывает Sync-настройки компании (workspace default) "
        "и включает опцию транскрибации голосовых сообщений."
    ),
    title_en="Sync: transcription defaults",
    description_en=(
        "The user opens company Sync defaults (workspace default) "
        "and enables voice message transcription."
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
    await sync_e2e_open_with_namespace(sync_ui, ui_page_system, unique_id, suffix="settings")
    await scenario.step(
        "Sync открыт",
        ui_page_system,
        label_en="Sync opened",
    )

    edit_modal = await sync_e2e_open_sync_defaults(ui_page_system)
    await expect(edit_modal.locator(".modal-title")).to_contain_text(
        re.compile(r"Sync-настройки пространства|Namespace sync settings")
    )
    await scenario.step(
        "Открыты настройки Sync компании",
        ui_page_system,
        label_en="Company Sync defaults opened",
    )

    transcribe_switch = edit_modal.locator(".row").filter(
        has_text=re.compile(r"Авто-транскрипция голосовых|Auto-transcribe voice messages")
    ).locator("platform-switch")
    await transcribe_switch.click()
    await expect(transcribe_switch).to_have_attribute("checked", "", timeout=15_000)
    await sync_e2e_click_platform_button(edit_modal, "Сохранить", "Save")
    await expect(edit_modal).to_be_hidden(timeout=30_000)
    await scenario.step(
        "Настройки Sync сохранены",
        ui_page_system,
        label_en="Sync defaults saved",
    )
