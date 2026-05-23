"""E2E: выбор платформенного пространства в Sync."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_e2e_seed_namespace,
    sync_e2e_select_namespace,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="sync",
    tag="spaces",
    doc_slug="create-space",
    title="Sync: выбор пространства",
    description=(
        "Пользователь открывает Sync и выбирает существующее платформенное пространство "
        "в селекторе сайдбара."
    ),
    title_en="Sync: selecting a space",
    description_en=(
        "The user opens Sync and selects an existing platform namespace "
        "from the sidebar selector."
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
    namespace = await sync_e2e_seed_namespace(unique_id, suffix="select")

    await sync_ui.open(ui_page_system)
    await sync_ui.expect_shell(ui_page_system)
    await scenario.step(
        "Открыт Sync со списком всех пространств",
        ui_page_system,
        label_en="Sync is open with all spaces selected",
    )

    await sync_e2e_select_namespace(ui_page_system, namespace)
    await expect(
        ui_page_system.locator("sync-channel-picker .empty").filter(
            has_text=re.compile(
                r"Нет каналов в выбранных пространствах|No channels in selected spaces"
            )
        )
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Пространство выбрано в сайдбаре",
        ui_page_system,
        label_en="Space is selected in the sidebar",
    )
