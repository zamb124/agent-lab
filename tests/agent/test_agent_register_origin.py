"""Register/discover origin: Host tenant и явный ?origin=."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from apps.agent.service import resolve_brand_frontend_base_url, resolve_frontend_base_url


def test_resolve_frontend_base_url_from_tenant_host() -> None:
    resolved = resolve_frontend_base_url(
        request_host="test-company.lvh.me:9004",
        url_scheme="http",
    )
    assert resolved == "http://test-company.lvh.me:9004"


def test_resolve_brand_frontend_base_url_for_catalog_host() -> None:
    assert resolve_brand_frontend_base_url("humanitec.ru") == "https://humanitec.ru"
    assert resolve_brand_frontend_base_url("linnex.io") == "https://linnex.io"
    assert resolve_brand_frontend_base_url("system.lvh.me:9004") is None


def test_resolve_frontend_base_url_explicit_origin() -> None:
    resolved = resolve_frontend_base_url(origin_override="http://system.lvh.me:9004")
    assert resolved == "http://system.lvh.me:9004"


def test_resolve_frontend_base_url_rejects_foreign_origin() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _ = resolve_frontend_base_url(origin_override="https://evil.example.com")
    assert exc_info.value.status_code == 400
