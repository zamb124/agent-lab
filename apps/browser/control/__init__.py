"""
Browser Control API: единый адаптер поверх Browser Runtime (§17.3).
"""

from __future__ import annotations

from apps.browser.control.contracts import BrowserControlAdapter
from apps.browser.control.factory import ControlBackendName, build_browser_control_adapter
from apps.browser.control.stub_adapters import AgentBrowserAdapter, BrowserUseAdapter
from apps.browser.control.playwright_adapter import PlaywrightAdapter
from apps.browser.control.types import (
    VISIBILITY_TREE_SCHEMA_VERSION,
    BrowserCapabilityError,
    BrowserControlFeatures,
)

__all__ = [
    "AgentBrowserAdapter",
    "BrowserCapabilityError",
    "BrowserControlAdapter",
    "BrowserControlFeatures",
    "BrowserUseAdapter",
    "ControlBackendName",
    "PlaywrightAdapter",
    "VISIBILITY_TREE_SCHEMA_VERSION",
    "build_browser_control_adapter",
]
