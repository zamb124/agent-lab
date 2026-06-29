"""E2E: анонимный просмотр по публичной ссылке Office."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.office_e2e_helpers import (
    office_api_create_catalog,
    office_api_enable_binding_public_link,
    office_api_upload_txt,
    office_e2e_goto_public_preview,
    office_e2e_set_locale_ru,
)
from tests.ui.e2e.sync_e2e_helpers import sync_e2e_seed_namespace
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="office",
    tag="public",
    doc_slug="public-link-preview",
    title="Office: просмотр по публичной ссылке",
    title_en="Office: public link preview",
    description="Анонимный доступ к документу по токену /documents/p/:token и обработка неверной ссылки.",
    description_en="Anonymous document access via /documents/p/:token and invalid link handling.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_office_public_link_preview(
    scenario: ScenarioRecorder,
    office_ui: AppUI,
    ui_page_anonymous: Page,
    unique_id: str,
    office_client_http,
    auth_headers_system,
    auth_token_system: str,
) -> None:
    doc_title = f"Public {unique_id}"

    namespace = await sync_e2e_seed_namespace(unique_id, suffix="public")
    catalog_id = await office_api_create_catalog(
        office_ui.origin,
        auth_token_system,
        unique_id,
        namespace=namespace,
        title_prefix="public",
    )
    binding_id = await office_api_upload_txt(
        office_client_http,
        auth_headers_system,
        namespace=namespace,
        catalog_id=catalog_id,
        title=doc_title,
        content=b"public preview content for office e2e",
    )
    token = await office_api_enable_binding_public_link(
        office_client_http,
        auth_headers_system,
        binding_id,
        namespace=namespace,
    )

    await office_e2e_set_locale_ru(ui_page_anonymous)
    await office_e2e_goto_public_preview(office_ui, ui_page_anonymous, token)
    await scenario.step(
        "Страница предпросмотра открыта",
        ui_page_anonymous,
        label_en="Preview page opened",
    )

    preview = ui_page_anonymous.locator("office-public-preview-page")
    await expect(preview).to_contain_text(doc_title, timeout=60_000)
    await scenario.step(
        "Документ виден без авторизации",
        ui_page_anonymous,
        label_en="Document visible without auth",
    )

    viewer = preview.locator("platform-document-viewer-host")
    await expect(viewer).to_be_visible(timeout=120_000)
    await scenario.step(
        "Просмотрщик документа загружен",
        ui_page_anonymous,
        label_en="Document viewer loaded",
    )

    await office_e2e_goto_public_preview(office_ui, ui_page_anonymous, "invalid-token-000")
    await expect(preview.get_by_text("Ссылка не найдена")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Некорректная ссылка отклонена",
        ui_page_anonymous,
        label_en="Invalid link rejected",
    )

    _ = binding_id
