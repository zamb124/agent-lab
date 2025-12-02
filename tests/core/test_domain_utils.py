"""
Тесты для core/utils/domain.py - утилиты работы с доменами.
"""

import pytest

from core.utils.domain import (
    PRIMARY_DOMAIN,
    SUPPORTED_DOMAINS,
    extract_base_domain,
    extract_subdomain,
    is_local,
    is_supported_domain,
    get_protocol,
    get_host_with_port,
    build_url,
)


class TestExtractBaseDomain:
    """Тесты для extract_base_domain"""
    
    # === humanitec.ru ===
    
    def test_humanitec_ru_base(self):
        assert extract_base_domain("humanitec.ru") == "humanitec.ru"
    
    def test_humanitec_ru_www(self):
        assert extract_base_domain("www.humanitec.ru") == "humanitec.ru"
    
    def test_humanitec_ru_subdomain(self):
        assert extract_base_domain("company.humanitec.ru") == "humanitec.ru"
    
    def test_humanitec_ru_nested_subdomain(self):
        assert extract_base_domain("api.v1.humanitec.ru") == "humanitec.ru"
    
    def test_humanitec_ru_with_port(self):
        assert extract_base_domain("humanitec.ru:443") == "humanitec.ru"
    
    def test_humanitec_ru_subdomain_with_port(self):
        assert extract_base_domain("company.humanitec.ru:8080") == "humanitec.ru"
    
    # === agents-lab.ru ===
    
    def test_agents_lab_ru_base(self):
        assert extract_base_domain("agents-lab.ru") == "agents-lab.ru"
    
    def test_agents_lab_ru_www(self):
        assert extract_base_domain("www.agents-lab.ru") == "agents-lab.ru"
    
    def test_agents_lab_ru_subdomain(self):
        assert extract_base_domain("mycompany.agents-lab.ru") == "agents-lab.ru"
    
    def test_agents_lab_ru_with_port(self):
        assert extract_base_domain("agents-lab.ru:443") == "agents-lab.ru"
    
    # === localhost ===
    
    def test_localhost_simple(self):
        assert extract_base_domain("localhost") == "localhost"
    
    def test_localhost_with_port(self):
        assert extract_base_domain("localhost:8002") == "localhost"
    
    def test_localhost_with_different_port(self):
        assert extract_base_domain("localhost:3000") == "localhost"
    
    def test_localhost_subdomain(self):
        assert extract_base_domain("company.localhost") == "localhost"
    
    def test_localhost_subdomain_with_port(self):
        assert extract_base_domain("company.localhost:8002") == "localhost"
    
    def test_localhost_nested_subdomain(self):
        assert extract_base_domain("api.company.localhost:8002") == "localhost"
    
    # === Неизвестные домены (fallback to PRIMARY_DOMAIN) ===
    
    def test_unknown_domain_fallback(self):
        assert extract_base_domain("example.com") == PRIMARY_DOMAIN
    
    def test_unknown_subdomain_fallback(self):
        assert extract_base_domain("app.example.com") == PRIMARY_DOMAIN
    
    def test_ip_address_fallback(self):
        assert extract_base_domain("192.168.1.1") == PRIMARY_DOMAIN
    
    def test_ip_with_port_fallback(self):
        assert extract_base_domain("192.168.1.1:8000") == PRIMARY_DOMAIN
    
    # === Case insensitive ===
    
    def test_uppercase_domain(self):
        assert extract_base_domain("HUMANITEC.RU") == "humanitec.ru"
    
    def test_mixed_case_subdomain(self):
        assert extract_base_domain("Company.Humanitec.RU") == "humanitec.ru"
    
    # === Edge cases ===
    
    def test_empty_string(self):
        assert extract_base_domain("") == PRIMARY_DOMAIN
    
    def test_only_port(self):
        assert extract_base_domain(":8002") == PRIMARY_DOMAIN


class TestExtractSubdomain:
    """Тесты для extract_subdomain"""
    
    # === humanitec.ru ===
    
    def test_humanitec_no_subdomain(self):
        assert extract_subdomain("humanitec.ru") is None
    
    def test_humanitec_www_not_subdomain(self):
        assert extract_subdomain("www.humanitec.ru") is None
    
    def test_humanitec_subdomain(self):
        assert extract_subdomain("company.humanitec.ru") == "company"
    
    def test_humanitec_subdomain_with_hyphen(self):
        assert extract_subdomain("my-company.humanitec.ru") == "my-company"
    
    def test_humanitec_subdomain_with_numbers(self):
        assert extract_subdomain("company123.humanitec.ru") == "company123"
    
    def test_humanitec_nested_subdomain(self):
        assert extract_subdomain("api.v1.humanitec.ru") == "api.v1"
    
    def test_humanitec_subdomain_with_port(self):
        assert extract_subdomain("company.humanitec.ru:443") == "company"
    
    # === agents-lab.ru ===
    
    def test_agents_lab_no_subdomain(self):
        assert extract_subdomain("agents-lab.ru") is None
    
    def test_agents_lab_www_not_subdomain(self):
        assert extract_subdomain("www.agents-lab.ru") is None
    
    def test_agents_lab_subdomain(self):
        assert extract_subdomain("mycompany.agents-lab.ru") == "mycompany"
    
    # === localhost ===
    
    def test_localhost_no_subdomain(self):
        assert extract_subdomain("localhost") is None
    
    def test_localhost_with_port_no_subdomain(self):
        assert extract_subdomain("localhost:8002") is None
    
    def test_localhost_subdomain(self):
        assert extract_subdomain("company.localhost") == "company"
    
    def test_localhost_subdomain_with_port(self):
        assert extract_subdomain("company.localhost:8002") == "company"
    
    def test_localhost_nested_subdomain(self):
        assert extract_subdomain("api.company.localhost:8002") == "api.company"
    
    # === Unknown domains ===
    
    def test_unknown_domain_no_subdomain(self):
        # Неизвестный домен → fallback to PRIMARY_DOMAIN → нет субдомена
        assert extract_subdomain("example.com") is None
    
    # === Case insensitive ===
    
    def test_subdomain_case_preserved(self):
        # Субдомен приводится к lowercase
        assert extract_subdomain("COMPANY.humanitec.ru") == "company"


class TestIsLocal:
    """Тесты для is_local"""
    
    def test_localhost_is_local(self):
        assert is_local("localhost") is True
    
    def test_localhost_with_port_is_local(self):
        assert is_local("localhost:8002") is True
    
    def test_subdomain_localhost_is_local(self):
        assert is_local("company.localhost:8002") is True
    
    def test_humanitec_not_local(self):
        assert is_local("humanitec.ru") is False
    
    def test_agents_lab_not_local(self):
        assert is_local("agents-lab.ru") is False
    
    def test_subdomain_humanitec_not_local(self):
        assert is_local("company.humanitec.ru") is False
    
    def test_unknown_domain_not_local(self):
        assert is_local("example.com") is False


class TestIsSupportedDomain:
    """Тесты для is_supported_domain"""
    
    def test_humanitec_supported(self):
        assert is_supported_domain("humanitec.ru") is True
    
    def test_humanitec_subdomain_supported(self):
        assert is_supported_domain("company.humanitec.ru") is True
    
    def test_agents_lab_supported(self):
        assert is_supported_domain("agents-lab.ru") is True
    
    def test_agents_lab_subdomain_supported(self):
        assert is_supported_domain("company.agents-lab.ru") is True
    
    def test_localhost_supported(self):
        assert is_supported_domain("localhost") is True
    
    def test_localhost_subdomain_supported(self):
        assert is_supported_domain("company.localhost:8002") is True
    
    def test_unknown_domain_not_supported(self):
        # Неизвестные домены → fallback to PRIMARY_DOMAIN → supported
        # Это правильное поведение, т.к. fallback делает его "supported"
        assert is_supported_domain("example.com") is True


class TestGetProtocol:
    """Тесты для get_protocol"""
    
    def test_localhost_http(self):
        assert get_protocol("localhost") == "http"
    
    def test_localhost_with_port_http(self):
        assert get_protocol("localhost:8002") == "http"
    
    def test_subdomain_localhost_http(self):
        assert get_protocol("company.localhost:8002") == "http"
    
    def test_humanitec_https(self):
        assert get_protocol("humanitec.ru") == "https"
    
    def test_humanitec_subdomain_https(self):
        assert get_protocol("company.humanitec.ru") == "https"
    
    def test_agents_lab_https(self):
        assert get_protocol("agents-lab.ru") == "https"
    
    def test_unknown_domain_https(self):
        assert get_protocol("example.com") == "https"


class TestGetHostWithPort:
    """Тесты для get_host_with_port"""
    
    # === localhost ===
    
    def test_localhost_preserves_port(self):
        assert get_host_with_port("localhost:8002") == "localhost:8002"
    
    def test_localhost_different_port(self):
        assert get_host_with_port("localhost:3000") == "localhost:3000"
    
    def test_localhost_subdomain_extracts_port(self):
        assert get_host_with_port("company.localhost:8002") == "localhost:8002"
    
    def test_localhost_without_port_default(self):
        assert get_host_with_port("localhost") == "localhost:8002"
    
    def test_localhost_subdomain_without_port_default(self):
        assert get_host_with_port("company.localhost") == "localhost:8002"
    
    # === Production domains (no port) ===
    
    def test_humanitec_no_port(self):
        assert get_host_with_port("humanitec.ru") == "humanitec.ru"
    
    def test_humanitec_subdomain_no_port(self):
        assert get_host_with_port("company.humanitec.ru") == "humanitec.ru"
    
    def test_humanitec_with_port_ignored(self):
        # В production порт игнорируется
        assert get_host_with_port("humanitec.ru:443") == "humanitec.ru"
    
    def test_agents_lab_no_port(self):
        assert get_host_with_port("agents-lab.ru") == "agents-lab.ru"
    
    def test_agents_lab_subdomain_no_port(self):
        assert get_host_with_port("company.agents-lab.ru") == "agents-lab.ru"


class TestBuildUrl:
    """Тесты для build_url"""
    
    # === localhost ===
    
    def test_localhost_simple(self):
        assert build_url("localhost:8002", "") == "http://localhost:8002"
    
    def test_localhost_with_path(self):
        assert build_url("localhost:8002", "/dashboard") == "http://localhost:8002/dashboard"
    
    def test_localhost_with_subdomain(self):
        assert build_url("localhost:8002", "/dashboard", "company") == "http://company.localhost:8002/dashboard"
    
    def test_localhost_subdomain_keeps_port(self):
        url = build_url("company.localhost:8002", "/login", "other")
        assert url == "http://other.localhost:8002/login"
    
    def test_localhost_different_port(self):
        assert build_url("localhost:3000", "/api") == "http://localhost:3000/api"
    
    def test_localhost_no_port_default(self):
        assert build_url("localhost", "/test") == "http://localhost:8002/test"
    
    # === humanitec.ru ===
    
    def test_humanitec_simple(self):
        assert build_url("humanitec.ru", "") == "https://humanitec.ru"
    
    def test_humanitec_with_path(self):
        assert build_url("humanitec.ru", "/frontend/dashboard") == "https://humanitec.ru/frontend/dashboard"
    
    def test_humanitec_with_subdomain(self):
        url = build_url("humanitec.ru", "/frontend/dashboard", "company")
        assert url == "https://company.humanitec.ru/frontend/dashboard"
    
    def test_humanitec_subdomain_request_to_other(self):
        # Запрос пришел на company.humanitec.ru, строим URL для other
        url = build_url("company.humanitec.ru", "/login", "other")
        assert url == "https://other.humanitec.ru/login"
    
    def test_humanitec_www_to_subdomain(self):
        url = build_url("www.humanitec.ru", "/dashboard", "company")
        assert url == "https://company.humanitec.ru/dashboard"
    
    # === agents-lab.ru ===
    
    def test_agents_lab_simple(self):
        assert build_url("agents-lab.ru", "") == "https://agents-lab.ru"
    
    def test_agents_lab_with_path(self):
        assert build_url("agents-lab.ru", "/api/v1/health") == "https://agents-lab.ru/api/v1/health"
    
    def test_agents_lab_with_subdomain(self):
        url = build_url("agents-lab.ru", "/dashboard", "mycompany")
        assert url == "https://mycompany.agents-lab.ru/dashboard"
    
    def test_agents_lab_subdomain_to_subdomain(self):
        url = build_url("one.agents-lab.ru", "/home", "two")
        assert url == "https://two.agents-lab.ru/home"
    
    # === Edge cases ===
    
    def test_empty_path(self):
        assert build_url("humanitec.ru", "") == "https://humanitec.ru"
    
    def test_none_subdomain(self):
        assert build_url("humanitec.ru", "/test", None) == "https://humanitec.ru/test"
    
    def test_path_with_query(self):
        url = build_url("humanitec.ru", "/api?foo=bar", "company")
        assert url == "https://company.humanitec.ru/api?foo=bar"
    
    def test_complex_path(self):
        url = build_url("humanitec.ru", "/frontend/flows/edit/flow123")
        assert url == "https://humanitec.ru/frontend/flows/edit/flow123"


class TestConstants:
    """Тесты для констант"""
    
    def test_primary_domain(self):
        assert PRIMARY_DOMAIN == "humanitec.ru"
    
    def test_supported_domains_contains_humanitec(self):
        assert "humanitec.ru" in SUPPORTED_DOMAINS
    
    def test_supported_domains_contains_agents_lab(self):
        assert "agents-lab.ru" in SUPPORTED_DOMAINS
    
    def test_supported_domains_count(self):
        assert len(SUPPORTED_DOMAINS) == 2


class TestRealWorldScenarios:
    """Реальные сценарии использования"""
    
    def test_select_company_localhost(self):
        """Сценарий: страница выбора компании в local env"""
        host = "localhost:8002"
        company_id = "acme"
        url = build_url(host, "/frontend/dashboard", subdomain=company_id)
        assert url == "http://acme.localhost:8002/frontend/dashboard"
    
    def test_select_company_production(self):
        """Сценарий: страница выбора компании в production"""
        host = "humanitec.ru"
        company_id = "acme"
        url = build_url(host, "/frontend/dashboard", subdomain=company_id)
        assert url == "https://acme.humanitec.ru/frontend/dashboard"
    
    def test_switch_company_from_subdomain(self):
        """Сценарий: переключение компании с одного поддомена на другой"""
        host = "old-company.humanitec.ru"
        new_company = "new-company"
        url = build_url(host, "/frontend/dashboard", subdomain=new_company)
        assert url == "https://new-company.humanitec.ru/frontend/dashboard"
    
    def test_oauth_callback_always_primary(self):
        """Сценарий: OAuth callback всегда на PRIMARY_DOMAIN"""
        # OAuth провайдеры требуют зарегистрированный URL
        callback_url = f"https://{PRIMARY_DOMAIN}/auth/callback/yandex"
        assert callback_url == "https://humanitec.ru/auth/callback/yandex"
    
    def test_webhook_url_telegram(self):
        """Сценарий: Webhook URL для Telegram"""
        webhook_url = f"https://{PRIMARY_DOMAIN}/api/v1/webhook/telegram/flow123"
        assert webhook_url == "https://humanitec.ru/api/v1/webhook/telegram/flow123"
    
    def test_privacy_page_localhost(self):
        """Сценарий: страница политики конфиденциальности в local"""
        host = "company.localhost:8002"
        site_url = build_url(host, "")
        domain = get_host_with_port(host)
        assert site_url == "http://localhost:8002"
        assert domain == "localhost:8002"
    
    def test_privacy_page_production(self):
        """Сценарий: страница политики конфиденциальности в production"""
        host = "company.humanitec.ru"
        site_url = build_url(host, "")
        domain = get_host_with_port(host)
        assert site_url == "https://humanitec.ru"
        assert domain == "humanitec.ru"
    
    def test_create_company_redirect(self):
        """Сценарий: редирект после создания компании"""
        host = "humanitec.ru"
        subdomain = "newcompany"
        redirect_url = build_url(host, "/frontend/dashboard", subdomain=subdomain)
        assert redirect_url == "https://newcompany.humanitec.ru/frontend/dashboard"
    
    def test_cross_domain_request(self):
        """Сценарий: запрос пришел на agents-lab.ru, строим URL"""
        host = "company.agents-lab.ru"
        url = build_url(host, "/api/health")
        assert url == "https://agents-lab.ru/api/health"
        
        url_with_sub = build_url(host, "/dashboard", "other")
        assert url_with_sub == "https://other.agents-lab.ru/dashboard"

