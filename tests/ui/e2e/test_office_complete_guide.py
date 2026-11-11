"""E2E-инструкция: полный маршрут по сервису Office (/documents)."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.office_e2e_helpers import (
    office_e2e_create_catalog_ui,
    office_e2e_create_empty_document,
    office_e2e_create_namespace_ui,
    office_e2e_expect_editor_loaded,
    office_e2e_expect_explorer,
    office_e2e_explorer,
    office_e2e_namespace_name,
    office_e2e_open,
    office_e2e_open_document_by_title,
    office_e2e_select_catalog,
    office_e2e_set_locale_ru,
    office_e2e_upload_file_ui,
)
from tests.ui.e2e.sync_e2e_helpers import sync_e2e_expect_ws_open
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="office",
    tag="getting-started",
    doc_slug="documents-complete-guide",
    title="Office: полная инструкция по сервису",
    title_en="Office: complete service guide",
    description=(
        "Полный рабочий маршрут Documents: пространство, каталог, создание документа, "
        "загрузка файла и открытие в редакторе OnlyOffice."
    ),
    description_en=(
        "Complete Documents workflow: workspace, catalog, create a document, "
        "upload a file, and open it in the OnlyOffice editor."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_office_complete_service_guide(
    scenario: ScenarioRecorder,
    office_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    tmp_path: Path,
    crm_service,
) -> None:
    _ = crm_service
    namespace = office_e2e_namespace_name(unique_id, suffix="guide")
    catalog_title = f"Каталог {unique_id}"
    doc_title = f"Договор {unique_id}"
    upload_title = f"Скрин {unique_id}.png"

    await office_e2e_set_locale_ru(ui_page_system)
    await office_e2e_open(office_ui, ui_page_system)
    await sync_e2e_expect_ws_open(ui_page_system)
    await scenario.step(
        "Открыт сервис Документы",
        ui_page_system,
        label_en="Documents service opened",
    )

    await office_e2e_create_namespace_ui(ui_page_system, namespace)
    await scenario.step(
        "Создано рабочее пространство",
        ui_page_system,
        label_en="Workspace created",
    )

    await office_e2e_create_catalog_ui(ui_page_system, catalog_title)
    await office_e2e_select_catalog(ui_page_system, catalog_title)
    await scenario.step(
        "Создан каталог документов",
        ui_page_system,
        label_en="Document catalog created",
    )

    await office_e2e_create_empty_document(ui_page_system, doc_title)
    await office_e2e_expect_editor_loaded(ui_page_system)
    await scenario.step(
        "Создан пустой документ Word",
        ui_page_system,
        label_en="Empty Word document created",
    )

    back = ui_page_system.locator("office-document-editor-page button.stage-back").first
    await back.click()
    await office_e2e_expect_explorer(ui_page_system)

    # Визуально отличное изображение: в просмотрщике сразу понятно,
    # что открыт загруженный файл, а не страница приложения.
    png_path = tmp_path / upload_title
    data_url = await ui_page_system.evaluate(
        """() => {
            const c = document.createElement('canvas');
            c.width = 1200;
            c.height = 800;
            const g = c.getContext('2d');
            const grad = g.createLinearGradient(0, 0, 1200, 800);
            grad.addColorStop(0, '#0ea5e9');
            grad.addColorStop(1, '#6366f1');
            g.fillStyle = grad;
            g.fillRect(0, 0, 1200, 800);
            g.fillStyle = '#ffffff';
            g.beginPath();
            g.arc(600, 300, 140, 0, Math.PI * 2);
            g.fill();
            g.fillStyle = '#0ea5e9';
            g.font = 'bold 110px system-ui';
            g.textAlign = 'center';
            g.textBaseline = 'middle';
            g.fillText('PNG', 600, 300);
            g.fillStyle = '#ffffff';
            g.font = '600 52px system-ui';
            g.fillText('Platform Documents', 600, 560);
            return c.toDataURL('image/png');
        }"""
    )
    png_path.write_bytes(base64.b64decode(data_url.split(",", 1)[1]))
    await office_e2e_upload_file_ui(ui_page_system, png_path)
    await expect(
        office_e2e_explorer(ui_page_system).locator("platform-file-row, platform-file-card").filter(
            has_text=upload_title.replace(".png", "")
        ).first
    ).to_be_visible(timeout=60_000)
    await scenario.step(
        "Файл загружен в каталог",
        ui_page_system,
        label_en="File uploaded to catalog",
    )

    await office_e2e_open_document_by_title(ui_page_system, upload_title.replace(".png", ""))
    await office_e2e_expect_editor_loaded(ui_page_system)
    viewer_img = ui_page_system.locator("platform-document-image-viewer img").first
    await expect(viewer_img).to_be_visible(timeout=60_000)
    await ui_page_system.wait_for_function(
        "img => img.complete && img.naturalWidth > 0",
        arg=await viewer_img.element_handle(),
    )
    await scenario.step(
        "Документ открыт в редакторе",
        ui_page_system,
        label_en="Document opened in editor",
    )

    await back.click()
    await office_e2e_expect_explorer(ui_page_system)
    await office_e2e_open_document_by_title(ui_page_system, doc_title)
    await office_e2e_expect_editor_loaded(ui_page_system)
    banner = ui_page_system.locator("office-integration-banner")
    if await banner.count() > 0:
        await expect(banner).to_be_visible(timeout=10_000)
    await scenario.step(
        "Редактор и интеграция OnlyOffice готовы",
        ui_page_system,
        label_en="Editor and OnlyOffice integration ready",
    )
