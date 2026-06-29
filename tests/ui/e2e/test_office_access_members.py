"""E2E: участники и доступ к каталогу Office."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.office_e2e_helpers import (
    office_api_setup_private_catalog,
    office_e2e_catalog_context_action,
    office_e2e_open_catalog_context_menu,
    office_e2e_open_with_namespace,
    office_e2e_select_catalog,
)
from tests.ui.e2e.sync_e2e_helpers import sync_e2e_click_platform_button
from tests.ui.harness import AppUI
from tests.ui.personas import UiTestUser
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="office",
    tag="access",
    doc_slug="catalog-access-and-members",
    title="Office: доступ и участники каталога",
    title_en="Office: catalog access and members",
    description="Приватный каталог, добавление и удаление участника, публичный каталог.",
    description_en="Private catalog, add and remove members, public catalog settings.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_office_catalog_access_and_members(
    scenario: ScenarioRecorder,
    office_ui: AppUI,
    ui_page_system: Page,
    ui_page_system_member: Page,
    unique_id: str,
    office_client_http,
    auth_headers_system,
    ui_user_system_member: UiTestUser,
    crm_service,
) -> None:
    _ = crm_service
    member_id = ui_user_system_member.user_id
    if not isinstance(member_id, str) or member_id == "":
        raise AssertionError("ui_user_system_member.user_id required")

    namespace = await office_e2e_open_with_namespace(office_ui, ui_page_system, unique_id, suffix="acc")
    catalog_id = await office_api_setup_private_catalog(
        office_client_http,
        auth_headers_system,
        unique_id,
        namespace=namespace,
        title_prefix="private-ui",
    )
    catalog_title = f"private-ui-{unique_id}"

    await office_e2e_select_catalog(ui_page_system, catalog_title)
    await office_e2e_open_catalog_context_menu(ui_page_system, catalog_title)
    members_item = ui_page_system.locator("office-catalog-context-menu .ctx-item").filter(
        has=ui_page_system.locator("platform-icon[name='users']")
    ).first
    await members_item.click()
    members_modal = ui_page_system.locator("office-catalog-members-modal")
    await expect(members_modal).to_be_visible(timeout=30_000)
    await scenario.step(
        "Модалка участников приватного каталога",
        ui_page_system,
        label_en="Private catalog members modal",
    )

    search = members_modal.locator("input.field-pill-input").first
    await search.fill(ui_user_system_member.name)
    candidate = members_modal.locator(".candidate-row").first
    await expect(candidate).to_be_visible(timeout=30_000)
    await candidate.click()
    await sync_e2e_click_platform_button(members_modal, "Закрыть", "Close")
    await expect(members_modal).to_be_hidden(timeout=30_000)
    await scenario.step(
        "Участник добавлен в каталог",
        ui_page_system,
        label_en="Member added to catalog",
    )

    await office_e2e_catalog_context_action(ui_page_system, catalog_title, "Редактировать", "Edit")
    edit_modal = ui_page_system.locator("office-catalog-edit-modal")
    public_switch = edit_modal.locator("platform-switch").first
    await public_switch.click()
    await sync_e2e_click_platform_button(edit_modal, "Сохранить", "Save")
    await expect(edit_modal).to_be_hidden(timeout=45_000)
    await scenario.step(
        "Каталог сделан общим для компании",
        ui_page_system,
        label_en="Catalog made company-visible",
    )

    await office_e2e_open_with_namespace(office_ui, ui_page_system_member, unique_id, suffix="acc")
    await office_e2e_select_catalog(ui_page_system_member, catalog_title)
    await expect(
        ui_page_system_member.locator("office-documents-explorer-page").filter(has_text=catalog_title)
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Участник компании видит каталог",
        ui_page_system_member,
        label_en="Company member sees catalog",
    )

    _ = catalog_id
