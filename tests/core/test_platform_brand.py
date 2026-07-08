"""Тесты platform brand resolver и domain utils."""

import pytest

from core.platform_brand.resolver import (
    UnknownPlatformDomainError,
    resolve_auth_apple_client_id,
    resolve_brand,
    resolve_embed_origins,
    resolve_flows_webhook_public_base_url,
    resolve_infrastructure_service_url,
    resolve_livekit_public_url,
    resolve_oauth_brand_origin,
    resolve_public_base_url,
    resolve_vapid_email,
    supported_domains,
)
from core.utils.domain import (
    extract_base_domain,
    is_allowed_integration_return_origin,
)


def test_supported_domains_include_linnex() -> None:
    domains = supported_domains()
    assert "humanitec.ru" in domains
    assert "linnex.io" in domains


def test_resolve_brand_humanitec() -> None:
    brand = resolve_brand("company.humanitec.ru")
    assert brand.platform_name == "Humanitec"


def test_resolve_brand_linnex() -> None:
    brand = resolve_brand("linnex.io")
    assert brand.platform_name == "Linnex"


def test_resolve_brand_unknown_raises() -> None:
    with pytest.raises(UnknownPlatformDomainError):
        resolve_brand("evil.example.com")


def test_extract_base_domain_linnex() -> None:
    assert extract_base_domain("acme.linnex.io") == "linnex.io"


def test_extract_base_domain_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unsupported host domain"):
        extract_base_domain("custom.internal:8002")


def test_resolve_public_base_url_linnex() -> None:
    assert resolve_public_base_url("linnex.io") == "https://linnex.io"


def test_resolve_livekit_public_url_linnex() -> None:
    assert resolve_livekit_public_url("acme.linnex.io") == "wss://livekit.linnex.io"


def test_resolve_infrastructure_service_url_onlyoffice_linnex() -> None:
    assert (
        resolve_infrastructure_service_url("acme.linnex.io", "onlyoffice")
        == "https://onlyoffice.linnex.io"
    )


def test_resolve_embed_origins_linnex() -> None:
    script_url, api_base = resolve_embed_origins("linnex.io")
    assert script_url == "https://cdn.linnex.io/lib/embed-chat/humanitec-embed-autoload.js"
    assert api_base == "https://api.linnex.io"


def test_resolve_flows_webhook_public_base_url_linnex() -> None:
    assert resolve_flows_webhook_public_base_url("linnex.io") == "https://linnex.io/flows"


def test_resolve_auth_apple_client_id_linnex() -> None:
    assert resolve_auth_apple_client_id("linnex.io") == "app.linnex.io"


def test_resolve_auth_apple_client_id_humanitec_fallback() -> None:
    client_id = resolve_auth_apple_client_id("humanitec.ru")
    assert client_id == "app.humanitec.ru"


def test_resolve_vapid_email_linnex() -> None:
    assert resolve_vapid_email("linnex.io") == "admin@linnex.io"


def test_resolve_oauth_brand_origin_from_host() -> None:
    assert resolve_oauth_brand_origin(brand_host="linnex.io") == "https://linnex.io"


def test_resolve_oauth_brand_origin_from_return_origin() -> None:
    assert (
        resolve_oauth_brand_origin(return_origin="https://acme.linnex.io/dashboard")
        == "https://linnex.io"
    )


def test_is_allowed_integration_return_origin_linnex() -> None:
    assert is_allowed_integration_return_origin("https://acme.linnex.io", "https://humanitec.ru") is True


def test_is_allowed_integration_return_origin_foreign_host() -> None:
    assert is_allowed_integration_return_origin("https://other.ru", "https://humanitec.ru") is False


def test_is_allowed_integration_return_origin_local_without_reference() -> None:
    assert is_allowed_integration_return_origin("http://system.lvh.me:8002", None) is True
