"""E2E: пространство и каталоги Office."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.office_e2e_helpers import (
    office_e2e_catalog_context_action,
    office_e2e_click_modal_button,
    office_e2e_create_catalog_ui,
    office_e2e_create_subcatalog_ui,
    office_e2e_open_with_namespace,
    office_e2e_select_catalog,
    office_e2e_tree,
)
from tests.ui.e2e.sync_e2e_helpers import sync_e2e_select_namespace
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="office",
    tag="catalogs",
    doc_slug="workspace-and-catalogs",
    title="Office: пространство и каталоги",
    title_en="Office: workspace and catalogs",
    description="Выбор пространства, создание корневого и вложенного каталога, редактирование и навигация по дереву.",
    description_en="Select workspace, create root and nested catalogs, edit settings, and navigate the tree.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_office_workspace_and_catalogs(
    scenario: ScenarioRecorder,
    office_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    root_title = f"Корень {unique_id}"
    child_title = f"Подкаталог {unique_id}"
    renamed_title = f"Архив {unique_id}"

    namespace = await office_e2e_open_with_namespace(
        office_ui, ui_page_system, unique_id, suffix="cat"
    )
    await scenario.step(
        "Выбрано рабочее пространство",
        ui_page_system,
        label_en="Workspace selected",
    )

    await office_e2e_create_catalog_ui(ui_page_system, root_title)
    await office_e2e_select_catalog(ui_page_system, root_title)
    await scenario.step(
        "Создан корневой каталог",
        ui_page_system,
        label_en="Root catalog created",
    )

    await office_e2e_create_subcatalog_ui(ui_page_system, root_title, child_title)
    await scenario.step(
        "Создан вложенный каталог",
        ui_page_system,
        label_en="Nested catalog created",
    )

    await office_e2e_catalog_context_action(ui_page_system, child_title, "Редактировать", "Edit")
    edit_modal = ui_page_system.locator("office-catalog-edit-modal")
    await expect(edit_modal).to_be_visible(timeout=30_000)
    await edit_modal.locator("input.field-pill-input").first.fill(renamed_title)
    await office_e2e_click_modal_button(edit_modal, "Сохранить", "Save")
    await expect(edit_modal).to_be_hidden(timeout=45_000)
    await scenario.step(
        "Каталог переименован",
        ui_page_system,
        label_en="Catalog renamed",
    )

    await office_e2e_select_catalog(ui_page_system, renamed_title)
    crumbs = ui_page_system.locator("office-file-toolbar .crumb")
    await expect(crumbs.first).to_be_visible(timeout=15_000)
    await sync_e2e_select_namespace(ui_page_system, namespace)
    await expect(office_e2e_tree(ui_page_system)).to_be_visible(timeout=15_000)
    await scenario.step(
        "Дерево каталогов и breadcrumbs",
        ui_page_system,
        label_en="Catalog tree and breadcrumbs",
    )
