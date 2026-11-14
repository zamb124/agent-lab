"""E2E: контекстное меню каталога открывается у кнопки, а не по host-relative координатам."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.office_e2e_helpers import (
    office_api_create_catalog,
    office_e2e_catalog_row,
    office_e2e_open_with_namespace,
)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_office_catalog_context_menu_anchor(
    office_ui,
    ui_page_system: Page,
    unique_id: str,
    auth_token_system: str,
    frontend_di,
) -> None:
    namespace = await office_e2e_open_with_namespace(
        office_ui, ui_page_system, unique_id, suffix="ctx", di=frontend_di
    )
    await office_api_create_catalog(
        office_ui.origin,
        auth_token_system,
        unique_id,
        namespace=namespace,
        title_prefix="ctx",
    )
    row = office_e2e_catalog_row(ui_page_system, f"ctx-{unique_id}")
    await expect(row).to_be_visible(timeout=45_000)
    await row.hover()
    menu_button = ui_page_system.locator(
        "office-explorer-tree button.mini-btn:has(platform-icon[name='more-vertical'])"
    ).first
    await expect(menu_button).to_be_visible(timeout=15_000)
    await menu_button.click()
    menu = ui_page_system.locator("office-catalog-context-menu platform-menu").first
    await expect(menu).to_be_visible(timeout=15_000)

    button_box = await menu_button.bounding_box()
    menu_box = await menu.bounding_box()
    if button_box is None or menu_box is None:
        raise AssertionError("context menu probe: bounding boxes required")
    vertical_gap = menu_box["y"] - (button_box["y"] + button_box["height"])
    if not -40 <= vertical_gap <= 40:
        raise AssertionError(
            f"menu opened far from button: gap {vertical_gap}px "
            f"(button y={button_box['y']}, menu y={menu_box['y']})"
        )
    horizontal_gap = menu_box["x"] - (button_box["x"] + button_box["width"])
    if horizontal_gap > 80 or menu_box["x"] + menu_box["width"] < button_box["x"]:
        raise AssertionError(
            f"menu detached horizontally: button x={button_box['x']} "
            f"w={button_box['width']}, menu x={menu_box['x']} w={menu_box['width']}"
        )
    await ui_page_system.screenshot(path="/tmp/ui_audit_shots/office/catalog_ctx_menu.png")
