"""
Фабрика BrowserControlAdapter по настройке backend.
"""

from __future__ import annotations

from typing import Protocol, assert_never

from apps.browser.adapters.playwright_control_adapter import PlaywrightAdapter
from apps.browser.adapters.stub_control_adapters import AgentBrowserAdapter, BrowserUseAdapter
from apps.browser.contracts.control import BrowserControlAdapter
from apps.browser.engine.playwright_interactor import PlaywrightBrowserInteractor
from apps.browser.engine.types import ControlBackend


class BrowserControlRuntime(Protocol):
    interactor: PlaywrightBrowserInteractor


def build_browser_control_adapter(
    *,
    backend: ControlBackend,
    facade: BrowserControlRuntime,
) -> BrowserControlAdapter:
    if backend == "playwright":
        return PlaywrightAdapter(facade.interactor)
    if backend == "browser_use":
        return BrowserUseAdapter()
    if backend == "agent_browser":
        return AgentBrowserAdapter()
    assert_never(backend)
