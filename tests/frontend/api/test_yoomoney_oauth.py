"""YooMoney OAuth callback URL host-aware (multi-brand)."""

from __future__ import annotations

import pytest
from starlette.requests import Request

from apps.frontend.api.yoomoney_oauth import _build_callback_url


def _request_with_host(host: str) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/frontend/api/billing/yoomoney/callback",
        "raw_path": b"/frontend/api/billing/yoomoney/callback",
        "query_string": b"",
        "headers": [(b"host", host.encode("utf-8"))],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "scheme": "https",
    }
    return Request(scope)


@pytest.mark.parametrize("host,expected_prefix", [
    ("humanitec.ru", "https://humanitec.ru/frontend/api/billing/yoomoney/callback"),
    ("linnex.io", "https://linnex.io/frontend/api/billing/yoomoney/callback"),
])
def test_build_callback_url_production_host(
    monkeypatch: pytest.MonkeyPatch,
    host: str,
    expected_prefix: str,
) -> None:
    import core.config.base as config_base

    config_base._settings_instance = None
    monkeypatch.setenv("SERVER__ENV", "production")
    request = _request_with_host(host)
    assert _build_callback_url(request) == expected_prefix
