"""Тесты разбора Host и локальных IP (OAuth, DevInterServiceProxy)."""

import pytest

from core.utils.domain import (
    extract_base_domain,
    extract_company_subdomain,
    extract_subdomain,
    get_cookie_domain,
    get_host_with_port,
    get_protocol,
    is_allowed_integration_return_origin,
    is_local,
    split_host_port,
)


@pytest.mark.parametrize(
    "host,hostname,port",
    [
        ("localhost:8002", "localhost", "8002"),
        ("127.0.0.1:8002", "127.0.0.1", "8002"),
        ("192.168.0.1:9000", "192.168.0.1", "9000"),
        ("humanitec.ru", "humanitec.ru", None),
        ("[::1]:8002", "::1", "8002"),
    ],
)
def test_split_host_port(host: str, hostname: str, port: str | None) -> None:
    h, p = split_host_port(host)
    assert h == hostname
    assert p == port


def test_extract_base_domain_ipv4_loopback() -> None:
    assert extract_base_domain("127.0.0.1:8002") == "127.0.0.1"


def test_extract_base_domain_private_ipv4() -> None:
    assert extract_base_domain("192.168.1.50:8002") == "192.168.1.50"


def test_get_host_with_port_ipv4() -> None:
    assert get_host_with_port("127.0.0.1:8002") == "127.0.0.1:8002"


def test_is_local_ipv4() -> None:
    assert is_local("127.0.0.1:8002") is True
    assert is_local("192.168.1.1:8002") is True


def test_get_protocol_local_ip() -> None:
    assert get_protocol("127.0.0.1:8002") == "http"


def test_get_cookie_domain_ip_is_none() -> None:
    assert get_cookie_domain("127.0.0.1:8002") is None


def test_get_cookie_domain_localhost_shared_across_subdomains() -> None:
    assert get_cookie_domain("localhost:8002") == "localhost"
    assert get_cookie_domain("company.localhost:8002") == "localhost"


def test_extract_subdomain_on_ip() -> None:
    assert extract_subdomain("127.0.0.1:8002") is None


def test_extract_company_subdomain_grafana_host_not_company() -> None:
    assert extract_subdomain("grafana.humanitec.ru") == "grafana"
    assert extract_company_subdomain("grafana.humanitec.ru") is None
    assert extract_company_subdomain("grafana.agents-lab.ru") is None


def test_extract_company_subdomain_company_unchanged() -> None:
    assert extract_company_subdomain("acme.humanitec.ru") == "acme"


def test_unknown_hostname_still_primary_domain() -> None:
    assert extract_base_domain("custom.internal:8002") == "humanitec.ru"


def test_is_allowed_integration_return_origin_lvh_subdomain() -> None:
    pub = "http://lvh.me:8002"
    assert is_allowed_integration_return_origin("http://system.lvh.me:8002", pub) is True
    assert is_allowed_integration_return_origin("http://lvh.me:8002", pub) is True
    assert is_allowed_integration_return_origin("https://system.lvh.me:8002", pub) is False
    assert is_allowed_integration_return_origin("http://evil.com:8002", pub) is False


def test_is_allowed_integration_return_origin_lvh_port_mismatch_local_dev() -> None:
    pub = "http://lvh.me:8002"
    assert is_allowed_integration_return_origin("http://system.lvh.me:8003", pub) is True


def test_is_allowed_integration_return_origin_prod_ports_must_match() -> None:
    pub = "https://humanitec.ru"
    assert is_allowed_integration_return_origin("https://acme.humanitec.ru:8443", pub) is False


def test_is_allowed_integration_return_origin_humanitec() -> None:
    pub = "https://humanitec.ru"
    assert is_allowed_integration_return_origin("https://acme.humanitec.ru", pub) is True
    assert is_allowed_integration_return_origin("https://other.ru", pub) is False
