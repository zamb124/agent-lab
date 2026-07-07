"""Playwright fixtures for UI Kit component playground."""

from __future__ import annotations

import pytest
import pytest_asyncio
from playwright.async_api import Locator, Page

from tests.ui.design_system_doc import ComponentDocRecorder


class UiKitPage:
    def __init__(self, page: Page, *, base_url: str) -> None:
        self.page = page
        self._base_url = base_url.rstrip("/")
        self._component = ""
        self._variant = ""

    async def load(self, component: str, variant: str) -> None:
        self._component = component
        self._variant = variant
        url = (
            f"{self._base_url}/frontend/design-system/preview"
            f"?component={component}&variant={variant}"
        )
        await self.page.goto(url, wait_until="domcontentloaded")
        await self.page.locator('[data-testid="ui-kit-root"]').wait_for(state="attached", timeout=30_000)

    @property
    def root_locator(self) -> Locator:
        if not self._component:
            raise ValueError("UiKitPage.load(component, variant) must be called first")
        return self.page.locator(f'[data-testid="ui-kit-root"] {self._component}')


@pytest_asyncio.fixture
async def component_doc(request: pytest.FixtureRequest) -> ComponentDocRecorder:
    rec = ComponentDocRecorder.from_pytest_node(request.node)
    yield rec
    rec.finalize()


@pytest_asyncio.fixture
async def ui_kit_page(page: Page, frontend_service) -> UiKitPage:
    _ = frontend_service
    return UiKitPage(page, base_url="http://localhost:9004")
