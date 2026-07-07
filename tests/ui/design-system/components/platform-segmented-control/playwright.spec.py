"""Playwright L2 doc scenario for platform-segmented-control."""

from __future__ import annotations

import pytest

from tests.ui.design_system_doc import ComponentDocRecorder


@pytest.mark.ui_component(
    service="platform",
    tag="ui-kit",
    component="platform-segmented-control",
    variant="default",
    doc_slug="platform-segmented-control",
)
@pytest.mark.asyncio
async def test_platform_segmented_control_default_gallery(
    ui_kit_page,
    component_doc: ComponentDocRecorder,
) -> None:
    await ui_kit_page.load("platform-segmented-control", "default")
    root = ui_kit_page.root_locator
    await root.wait_for(state="visible", timeout=15_000)
    await component_doc.step("Компонент смонтирован в playground", page=ui_kit_page.page)
    await component_doc.screenshot(page=ui_kit_page.page)
    await component_doc.step("Variant default отображается", page=ui_kit_page.page)
