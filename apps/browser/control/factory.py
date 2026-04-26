"""
Фабрика BrowserControlAdapter по настройке backend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from apps.browser.control.contracts import BrowserControlAdapter
from apps.browser.control.playwright_adapter import PlaywrightAdapter
from apps.browser.control.stub_adapters import AgentBrowserAdapter, BrowserUseAdapter

if TYPE_CHECKING:
    from apps.browser.runtime.facade import BrowserRuntimeFacade

ControlBackendName = Literal["playwright", "browser_use", "agent_browser"]


def build_browser_control_adapter(
    *,
    backend: ControlBackendName,
    facade: BrowserRuntimeFacade,
) -> BrowserControlAdapter:
    if backend == "playwright":
        return PlaywrightAdapter(facade.interactor)
    if backend == "browser_use":
        return BrowserUseAdapter()
    if backend == "agent_browser":
        return AgentBrowserAdapter()
    raise ValueError(f"Неизвестный control backend: {backend}")
