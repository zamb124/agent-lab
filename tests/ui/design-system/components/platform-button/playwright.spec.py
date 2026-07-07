"""Playwright L2 doc scenario for platform-button."""

from __future__ import annotations

import pytest

from tests.ui.design_system_doc import ComponentDocRecorder


@pytest.mark.ui_component(
    service="platform",
    tag="ui-kit",
    component="platform-button",
    variant="default",
    doc_slug="platform-button",
)
@pytest.mark.asyncio
async def test_platform_button_default_gallery(
    ui_kit_page,
    component_doc: ComponentDocRecorder,
) -> None:
    await ui_kit_page.load("platform-button", "default")
    root = ui_kit_page.root_locator
    await root.wait_for(state="visible", timeout=15_000)
    await component_doc.step("Компонент смонтирован в playground", page=ui_kit_page.page)
    await component_doc.screenshot(page=ui_kit_page.page)
    await component_doc.step("Variant default отображается", page=ui_kit_page.page)
