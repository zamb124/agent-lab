"""
Фабрика BrowserControlAdapter по настройке backend.
"""

from __future__ import annotations

from typing import Protocol, assert_never

from apps.browser.models.control import BrowserControlAdapter
from apps.browser.models.types import ControlBackend
from apps.browser.services.playwright_control_adapter import PlaywrightAdapter
from apps.browser.services.playwright_interactor import PlaywrightBrowserInteractor
from apps.browser.services.stub_control_adapters import AgentBrowserAdapter, BrowserUseAdapter


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
