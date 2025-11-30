"""
E2E тесты публичных страниц frontend.

Страницы доступны без авторизации:
- Landing page (/)
- Privacy policy (/privacy)
- Terms of service (/terms)
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.playwright
class TestLandingPage:
    """Тесты главной страницы (landing)"""

    def test_landing_page_loads(self, page: Page, server_url: str):
        """Главная страница загружается"""
        page.goto(server_url)
        page.wait_for_load_state("domcontentloaded")
        
        # Проверяем что title не пустой
        assert page.title(), "Страница должна иметь title"

    def test_landing_has_navigation(self, page: Page, server_url: str):
        """На странице есть навигация"""
        page.goto(server_url)
        
        nav = page.locator("nav, header, .navbar, .navigation, [role='navigation']")
        expect(nav.first).to_be_visible(timeout=10000)

    def test_landing_has_auth_link(self, page: Page, server_url: str):
        """На странице есть ссылка на авторизацию"""
        page.goto(server_url)
        
        auth_link = page.locator("a[href*='auth'], a[href*='login'], button:has-text('Войти'), a:has-text('Войти')")
        expect(auth_link.first).to_be_visible(timeout=10000)

    def test_landing_language_switcher(self, page: Page, server_url: str):
        """Переключатель языка работает"""
        page.goto(server_url)
        
        lang_switcher = page.locator("[data-language], .language-switcher, select[name='language']")
        if lang_switcher.count() > 0:
            expect(lang_switcher.first).to_be_visible()


@pytest.mark.playwright
class TestPrivacyPage:
    """Тесты страницы политики конфиденциальности"""

    def test_privacy_page_loads(self, page: Page, server_url: str):
        """Страница политики конфиденциальности загружается"""
        page.goto(f"{server_url}/privacy")
        page.wait_for_load_state("domcontentloaded")
        
        assert page.title(), "Страница должна иметь title"

    def test_privacy_has_content(self, page: Page, server_url: str):
        """На странице есть контент"""
        page.goto(f"{server_url}/privacy")
        page.wait_for_load_state("domcontentloaded")
        
        # Проверяем что на странице есть текстовый контент
        body = page.locator("body")
        expect(body).to_be_visible(timeout=10000)
        assert len(page.content()) > 500, "Страница должна иметь контент"

    def test_privacy_with_lang_param(self, page: Page, server_url: str):
        """Страница работает с параметром языка"""
        page.goto(f"{server_url}/privacy?lang=en")
        page.wait_for_load_state("domcontentloaded")
        assert page.title()
        
        page.goto(f"{server_url}/privacy?lang=ru")
        page.wait_for_load_state("domcontentloaded")
        assert page.title()


@pytest.mark.playwright
class TestTermsPage:
    """Тесты страницы пользовательского соглашения"""

    def test_terms_page_loads(self, page: Page, server_url: str):
        """Страница соглашения загружается"""
        page.goto(f"{server_url}/terms")
        page.wait_for_load_state("domcontentloaded")
        
        assert page.title(), "Страница должна иметь title"

    def test_terms_has_content(self, page: Page, server_url: str):
        """На странице есть контент"""
        page.goto(f"{server_url}/terms")
        page.wait_for_load_state("domcontentloaded")
        
        # Проверяем что на странице есть текстовый контент
        body = page.locator("body")
        expect(body).to_be_visible(timeout=10000)
        assert len(page.content()) > 500, "Страница должна иметь контент"

    def test_terms_with_lang_param(self, page: Page, server_url: str):
        """Страница работает с параметром языка"""
        page.goto(f"{server_url}/terms?lang=en")
        page.wait_for_load_state("domcontentloaded")
        assert page.title()
        
        page.goto(f"{server_url}/terms?lang=ru")
        page.wait_for_load_state("domcontentloaded")
        assert page.title()


@pytest.mark.playwright
class TestHealthEndpoint:
    """Тесты health endpoint"""

    def test_health_endpoint(self, page: Page, server_url: str):
        """Health endpoint возвращает статус"""
        response = page.request.get(f"{server_url}/health")
        
        assert response.ok
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "frontend"

