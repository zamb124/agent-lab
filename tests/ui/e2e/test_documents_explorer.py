"""E2E: Documents file explorer (Untitled UI pattern)."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="office",
    doc_slug="documents-explorer",
    title="Документы: file explorer",
    description="Главная страница /documents — explorer с деревом каталогов или empty state.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_documents_explorer_shell_loads(
    scenario: ScenarioRecorder,
    office_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await office_ui.open(ui_page_system)
    await scenario.step("SPA Документы открыт", ui_page_system)
    await office_ui.expect_shell(ui_page_system)
    explorer = ui_page_system.locator("office-documents-explorer-page")
    await expect(explorer).to_be_visible(timeout=30_000)
    tree = explorer.locator("office-explorer-tree")
    toolbar = explorer.locator("office-file-toolbar")
    empty_state = explorer.get_by_text(re.compile(r"Пока нет каталогов|No catalogs yet"))
    await expect(tree.or_(empty_state)).to_be_visible(timeout=30_000)
    await expect(toolbar.or_(empty_state)).to_be_visible(timeout=30_000)
    await scenario.step("File explorer загружен", ui_page_system)
