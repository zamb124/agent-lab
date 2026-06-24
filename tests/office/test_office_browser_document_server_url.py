from __future__ import annotations

from collections.abc import Mapping

from starlette.requests import Request

from apps.office.services.viewer_service import browser_document_server_url as _browser_document_server_url


def _request(
    *,
    scheme: str = "https",
    headers: Mapping[str, str] | None = None,
) -> Request:
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": scheme,
            "server": ("system.humanitec.ru", 443 if scheme == "https" else 80),
            "path": "/documents/api/v1/documents/binding/editor-config",
            "headers": raw_headers,
        }
    )


def test_browser_document_server_url_upgrades_external_http_on_https_request():
    request = _request(headers={"x-forwarded-proto": "https"})

    assert (
        _browser_document_server_url("http://onlyoffice.humanitec.ru/", request)
        == "https://onlyoffice.humanitec.ru"
    )


def test_browser_document_server_url_remaps_localhost_to_request_origin():
    request = _request(headers={"x-forwarded-proto": "https"})

    assert _browser_document_server_url("http://localhost:8002", request) == "https://system.humanitec.ru"


def test_browser_document_server_url_keeps_http_for_http_request():
    request = _request(scheme="http")

    assert (
        _browser_document_server_url("http://onlyoffice.humanitec.ru", request)
        == "http://onlyoffice.humanitec.ru"
    )
