"""Настройки Browser Runtime → view."""

from types import SimpleNamespace

import pytest

from apps.browser.config import BrowserRuntimeIntegrationConfig, settings_to_runtime_view


def test_settings_to_runtime_view_requires_cdp() -> None:
    cfg = BrowserRuntimeIntegrationConfig(cdp_url="", cdp_endpoints={})
    fake = SimpleNamespace(browser=cfg)
    with pytest.raises(ValueError, match="CDP endpoint"):
        settings_to_runtime_view(fake)


def test_settings_to_runtime_view_from_cdp_url() -> None:
    cfg = BrowserRuntimeIntegrationConfig(
        default_endpoint_key="default",
        cdp_url="http://127.0.0.1:9222",
    )
    fake = SimpleNamespace(browser=cfg)
    view = settings_to_runtime_view(fake)
    assert view.cdp_urls_by_endpoint["default"] == "http://127.0.0.1:9222"
    assert view.control_backend == "playwright"


def test_settings_to_runtime_view_requires_default_endpoint_key_in_map() -> None:
    cfg = BrowserRuntimeIntegrationConfig(
        default_endpoint_key="default",
        cdp_url="",
        cdp_endpoints={"secondary": "ws://127.0.0.1:9223"},
    )
    fake = SimpleNamespace(browser=cfg)
    with pytest.raises(ValueError, match="default_endpoint_key"):
        settings_to_runtime_view(fake)
