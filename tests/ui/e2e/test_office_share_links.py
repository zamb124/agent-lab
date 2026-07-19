"""E2E: публичные ссылки на каталог и документ Office."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.office_e2e_helpers import (
    office_api_create_catalog,
    office_api_upload_txt,
    office_e2e_catalog_context_action,
    office_e2e_open_with_namespace,
    office_e2e_select_catalog,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="office",
    tag="access",
    doc_slug="share-catalog-and-document",
    title="Office: доступ и публичная ссылка",
    title_en="Office: access and public link",
    description="Модалка доступа: включение ссылки, копирование, ротация и доступ к документу.",
    description_en="Access modal: enable link, copy, rotate, and document-level sharing.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_office_share_catalog_and_document(
    scenario: ScenarioRecorder,
    office_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    office_client_http,
    auth_headers_system,
    auth_token_system: str,
) -> None:
    catalog_title = f"share-{unique_id}"
    doc_title = f"PublicDoc {unique_id}"

    namespace = await office_e2e_open_with_namespace(office_ui, ui_page_system, unique_id, suffix="share")
    catalog_id = await office_api_create_catalog(
        office_ui.origin,
        auth_token_system,
        unique_id,
        namespace=namespace,
        title_prefix="share",
    )
    file_id = await office_api_upload_txt(
        office_client_http,
        auth_headers_system,
        namespace=namespace,
        catalog_id=catalog_id,
        title=doc_title,
    )
    await ui_page_system.reload(wait_until="domcontentloaded")
    await office_e2e_select_catalog(ui_page_system, catalog_title)
    await scenario.step(
        "Каталог с документом готов",
        ui_page_system,
        label_en="Catalog with document ready",
    )

    await office_e2e_catalog_context_action(ui_page_system, catalog_title, "Доступ", "Access")
    access_modal = ui_page_system.locator("office-access-modal")
    await expect(access_modal).to_be_visible(timeout=30_000)
    await scenario.step(
        "Модалка доступа к каталогу",
        ui_page_system,
        label_en="Catalog access modal",
    )

    link_switch = access_modal.locator(".switch-row").filter(
        has_text=re.compile(r"Любой по ссылке|Anyone with the link")
    ).locator("platform-switch").first
    await expect(link_switch).to_be_visible(timeout=15_000)
    switch_control = link_switch.get_by_role("switch")
    if await switch_control.get_attribute("aria-checked") != "true":
        await link_switch.click()
    rotate_btn = access_modal.get_by_role(
        "button", name=re.compile(r"Обновить ссылку|Rotate link")
    ).first
    await expect(rotate_btn).to_be_visible(timeout=15_000)
    await access_modal.get_by_role("button", name=re.compile(r"Сохранить|Save")).click()
    await expect(access_modal).to_be_hidden(timeout=45_000)
    await scenario.step(
        "Публичная ссылка включена",
        ui_page_system,
        label_en="Public link enabled",
    )

    await office_e2e_catalog_context_action(ui_page_system, catalog_title, "Доступ", "Access")
    access_modal = ui_page_system.locator("office-access-modal")
    await expect(access_modal).to_be_visible(timeout=30_000)
    rotate_btn = access_modal.get_by_role(
        "button", name=re.compile(r"Обновить ссылку|Rotate link")
    ).first
    await expect(rotate_btn).to_be_visible(timeout=30_000)
    link_url = access_modal.locator(".link-url")
    for _attempt in range(3):
        await rotate_btn.click()
        try:
            await expect(link_url).to_be_visible(timeout=20_000)
            break
        except AssertionError:
            if _attempt == 2:
                raise
            await ui_page_system.wait_for_timeout(500)

    await access_modal.get_by_role(
        "button", name=re.compile(r"Скопировать ссылку|Copy link|Copy share link")
    ).click()
    await scenario.step(
        "Ссылка скопирована",
        ui_page_system,
        label_en="Link copied",
    )

    await rotate_btn.click()
    await expect(access_modal.locator(".link-url")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Ссылка обновлена",
        ui_page_system,
        label_en="Link rotated",
    )

    link_switch = access_modal.locator(".switch-row").filter(
        has_text=re.compile(r"Любой по ссылке|Anyone with the link|ссылке", re.I)
    ).locator("platform-switch").first
    await link_switch.get_by_role("switch").click()
    await access_modal.get_by_role("button", name=re.compile(r"Сохранить|Save")).click()
    await expect(access_modal).to_be_hidden(timeout=45_000)
    await scenario.step(
        "Публичная ссылка отключена",
        ui_page_system,
        label_en="Public link disabled",
    )

    row = ui_page_system.locator("platform-file-row").filter(has_text=doc_title).first
    await row.locator("office-file-actions-menu button.trigger").click()
    await ui_page_system.locator("office-file-actions-menu .item").filter(has_text="Доступ").click()
    doc_access = ui_page_system.locator("office-access-modal")
    await expect(doc_access).to_be_visible(timeout=30_000)
    await scenario.step(
        "Доступ к отдельному документу",
        ui_page_system,
        label_en="Document-level access",
    )

    _ = file_id
