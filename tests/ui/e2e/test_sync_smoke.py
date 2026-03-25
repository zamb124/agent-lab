"""Дымовой E2E: Sync UI с реального HTTP (sync_service + sync_worker)."""

from __future__ import annotations

import pytest
from playwright.async_api import Page

from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="sync",
    title="Sync: загрузка оболочки чата",
    description=(
        "После входа под системным пользователем открывается SPA Sync; "
        "на экране отображается корневой элемент приложения (sync-app)."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_sync_chat_shell(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await sync_ui.open(ui_page_system)
    await scenario.step("Приложение Sync открыто по URL SPA", ui_page_system)
    await sync_ui.expect_shell(ui_page_system)
    await scenario.step("Оболочка sync-app отображается", ui_page_system)
