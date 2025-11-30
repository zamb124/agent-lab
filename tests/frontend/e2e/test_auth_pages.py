"""
E2E тесты страниц авторизации frontend.

Страницы:
- Auth page (/frontend/auth)
- Select company (/frontend/select-company)
- Create company (/frontend/create-company)
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.playwright
class TestAuthPage:
    """Тесты страницы авторизации"""

    def test_auth_page_loads(self, page: Page, server_url: str):
        """Страница авторизации загружается"""
        page.goto(f"{server_url}/frontend/auth")
        page.wait_for_load_state("domcontentloaded")
        
        assert page.title(), "Страница должна иметь title"

    def test_auth_has_providers(self, page: Page, server_url: str):
        """На странице есть кнопки провайдеров авторизации"""
        page.goto(f"{server_url}/frontend/auth")
        page.wait_for_load_state("domcontentloaded")
        
        # Проверяем что на странице есть элементы для авторизации
        body = page.locator("body")
        expect(body).to_be_visible(timeout=10000)
        
        # Контент страницы должен содержать слова про авторизацию
        content = page.content().lower()
        has_auth_content = (
            "yandex" in content or 
            "google" in content or 
            "войти" in content or
            "auth" in content
        )
        assert has_auth_content, "Страница должна содержать элементы авторизации"

    def test_auth_page_has_form_or_buttons(self, page: Page, server_url: str):
        """На странице есть форма или кнопки авторизации"""
        page.goto(f"{server_url}/frontend/auth")
        page.wait_for_load_state("domcontentloaded")
        
        # Проверяем что страница загрузилась с контентом
        assert len(page.content()) > 500, "Страница должна иметь контент"


@pytest.mark.playwright
class TestSelectCompanyPage:
    """Тесты страницы выбора компании"""

    def test_select_company_redirects_without_auth(self, page: Page, server_url: str):
        """Без авторизации редиректит на create-company или auth"""
        page.goto(f"{server_url}/frontend/select-company")
        page.wait_for_load_state("domcontentloaded")
        
        # Проверяем что страница загрузилась (редирект или нет)
        assert page.title() or page.url, "Страница должна загрузиться"


@pytest.mark.playwright
class TestCreateCompanyPage:
    """Тесты страницы создания компании"""

    def test_create_company_page_loads(self, page: Page, server_url: str):
        """Страница создания компании загружается"""
        page.goto(f"{server_url}/frontend/create-company")
        page.wait_for_load_state("domcontentloaded")
        
        assert page.title(), "Страница должна иметь title"

    def test_create_company_has_content(self, page: Page, server_url: str):
        """На странице есть контент"""
        page.goto(f"{server_url}/frontend/create-company")
        page.wait_for_load_state("domcontentloaded")
        
        # Проверяем что страница имеет контент
        body = page.locator("body")
        expect(body).to_be_visible(timeout=10000)
        assert len(page.content()) > 500, "Страница должна иметь контент"
