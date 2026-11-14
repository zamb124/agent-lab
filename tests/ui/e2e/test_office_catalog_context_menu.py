"""E2E: контекстное меню каталога открывается у кнопки, а не по host-relative координатам."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from playwright.async_api import Page, expect

from apps.frontend.di import FrontendDi
from core.di import require_di
from tests.ui.e2e.office_e2e_helpers import (
    office_api_create_catalog,
    office_e2e_catalog_row,
    office_e2e_open_with_namespace,
)
from tests.ui.harness import AppUI


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_office_catalog_context_menu_anchor(
    office_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    auth_token_system: str,
    frontend_app: FastAPI,
) -> None:
    namespace = await office_e2e_open_with_namespace(
        office_ui,
        ui_page_system,
        unique_id,
        suffix="ctx",
        di=require_di(frontend_app, FrontendDi),
    )
    _ = await office_api_create_catalog(
        office_ui.origin,
        auth_token_system,
        unique_id,
        namespace=namespace,
        title_prefix="ctx",
        company_visible=False,
    )
    _ = await ui_page_system.reload(wait_until="domcontentloaded")
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
            + f"(button y={button_box['y']}, menu y={menu_box['y']})"
        )
    horizontal_gap = menu_box["x"] - (button_box["x"] + button_box["width"])
    if horizontal_gap > 80 or menu_box["x"] + menu_box["width"] < button_box["x"]:
        raise AssertionError(
            f"menu detached horizontally: button x={button_box['x']} "
            + f"w={button_box['width']}, menu x={menu_box['x']} w={menu_box['width']}"
        )
    # Приватный каталог: в меню обязателен пункт «Участники» — без дубля «Доступ/Доступ».
    await expect(menu.get_by_text("Участники", exact=True)).to_be_visible(timeout=10_000)
    _ = await ui_page_system.screenshot(path="/tmp/ui_audit_shots/office/catalog_ctx_menu.png")
