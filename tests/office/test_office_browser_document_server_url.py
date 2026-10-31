from __future__ import annotations

import pytest

from apps.office.services.viewer_service import browser_document_server_url


def test_browser_document_server_url_upgrades_external_http_on_https_origin():
    assert (
        browser_document_server_url("http://onlyoffice.linnex.io/", "https://system.linnex.io")
        == "https://onlyoffice.linnex.io"
    )


def test_browser_document_server_url_remaps_localhost_to_public_origin():
    assert (
        browser_document_server_url("http://localhost:8002", "https://system.linnex.io")
        == "https://system.linnex.io"
    )


def test_browser_document_server_url_keeps_http_for_http_origin():
    assert (
        browser_document_server_url("http://onlyoffice.linnex.io", "http://system.linnex.io")
        == "http://onlyoffice.linnex.io"
    )


def test_browser_document_server_url_resolves_onlyoffice_subdomain_for_linnex_brand():
    assert (
        browser_document_server_url("https://onlyoffice.linnex.io", "https://system.linnex.io")
        == "https://onlyoffice.linnex.io"
    )


def test_browser_document_server_url_rejects_origin_without_scheme():
    with pytest.raises(ValueError, match="public_origin"):
        _ = browser_document_server_url("http://onlyoffice.linnex.io", "system.linnex.io")
