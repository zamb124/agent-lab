"""
Фабрика BrowserControlAdapter по настройке backend.
"""

from __future__ import annotations

from typing import Literal, Protocol

from apps.browser.adapters.playwright_control_adapter import PlaywrightAdapter
from apps.browser.adapters.stub_control_adapters import AgentBrowserAdapter, BrowserUseAdapter
from apps.browser.contracts.control import BrowserControlAdapter
from apps.browser.engine.playwright_interactor import PlaywrightBrowserInteractor

ControlBackendName = Literal["playwright", "browser_use", "agent_browser"]


class BrowserControlRuntime(Protocol):
    interactor: PlaywrightBrowserInteractor


def build_browser_control_adapter(
    *,
    backend: ControlBackendName,
    facade: BrowserControlRuntime,
) -> BrowserControlAdapter:
    if backend == "playwright":
        return PlaywrightAdapter(facade.interactor)
    if backend == "browser_use":
        return BrowserUseAdapter()
    if backend == "agent_browser":
        return AgentBrowserAdapter()
    raise ValueError(f"Неизвестный control backend: {backend}")
