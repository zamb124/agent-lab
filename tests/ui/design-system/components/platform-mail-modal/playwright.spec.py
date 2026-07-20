"""Playwright L2 smoke for platform-mail-modal."""

from __future__ import annotations

import pytest

from tests.ui.design_system_doc import ComponentDocRecorder


@pytest.mark.ui_component(
    service="platform",
    tag="ui-kit",
    component="platform-mail-modal",
    variant="default",
    doc_slug="platform-mail-modal",
)
@pytest.mark.asyncio
async def test_platform_mail_modal_default_gallery(
    ui_kit_page,
    component_doc: ComponentDocRecorder,
) -> None:
    await ui_kit_page.load("platform-mail-modal", "default")
    root = ui_kit_page.root_locator
    await root.wait_for(state="visible", timeout=15_000)
    await component_doc.step("Mail modal смонтирован в playground", page=ui_kit_page.page)
    await component_doc.screenshot(page=ui_kit_page.page)

    search = root.locator(".list-search")
    if await search.count() > 0:
        await search.first.wait_for(state="visible", timeout=5_000)
        await component_doc.step("Поиск писем виден", page=ui_kit_page.page)

    refresh = root.locator('platform-button[aria-label], platform-button').filter(
        has=ui_kit_page.page.locator('platform-icon[name="refresh"]')
    )
    if await refresh.count() > 0:
        await component_doc.step("Кнопка refresh/sync доступна", page=ui_kit_page.page)

    trash_icon = root.locator('platform-icon[name="trash"]')
    archive_btn = root.locator("platform-button").filter(
        has=ui_kit_page.page.locator('platform-icon[name="folder"]')
    )
    if await trash_icon.count() > 0 or await archive_btn.count() > 0:
        await component_doc.step("Triage-кнопки (trash/archive) в разметке", page=ui_kit_page.page)

    role_badge = root.locator(".att-badge")
    if await role_badge.count() > 0:
        await component_doc.step("Role badge в rail/settings", page=ui_kit_page.page)

    await component_doc.step("Variant default smoke завершён", page=ui_kit_page.page)
