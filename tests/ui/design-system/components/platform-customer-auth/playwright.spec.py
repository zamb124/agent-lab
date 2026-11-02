"""Playwright L2 doc scenario for platform-customer-auth."""

from __future__ import annotations

import pytest
from playwright.async_api import expect

from tests.ui.design_system_doc import ComponentDocRecorder


@pytest.mark.ui_component(
    service="platform",
    tag="ui-kit",
    component="platform-customer-auth",
    variant="default",
    doc_slug="platform-customer-auth",
)
@pytest.mark.asyncio
async def test_platform_customer_auth_default_gallery(
    ui_kit_page,
    component_doc: ComponentDocRecorder,
) -> None:
    """Покупатель открывает лист авторизации и вводит телефон."""
    await ui_kit_page.load("platform-customer-auth", "default")
    root = ui_kit_page.root_locator
    await root.wait_for(state="attached", timeout=15_000)
    await component_doc.step("Компонент смонтирован в playground", page=ui_kit_page.page)
    await ui_kit_page.page.evaluate(
        "document.querySelector('platform-customer-auth').open()"
    )
    phone_input = root.locator("input[type=tel]")
    await expect(phone_input).to_be_visible(timeout=15_000)
    await component_doc.step(
        "open() показывает лист с вводом телефона",
        page=ui_kit_page.page,
    )
    await phone_input.fill("+7 999")
    await root.locator("button.primary").click()
    await component_doc.step(
        "Некорректный номер — ошибка валидации в листе",
        page=ui_kit_page.page,
    )
    await component_doc.screenshot(page=ui_kit_page.page)
