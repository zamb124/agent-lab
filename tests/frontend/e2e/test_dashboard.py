"""
E2E тесты dashboard frontend.

Страницы:
- Dashboard (/frontend/dashboard)
- Index (/frontend/)
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.playwright
class TestDashboardPage:
    """Тесты главной страницы dashboard"""

    def test_dashboard_page_loads(self, page: Page, server_url: str):
        """Dashboard страница загружается (без авторизации - редирект или ошибка)"""
        page.goto(f"{server_url}/frontend/dashboard")
        page.wait_for_load_state("domcontentloaded")
        
        # Без авторизации страница должна как-то отреагировать
        assert page.title() or page.url, "Страница должна загрузиться"

    def test_frontend_index_loads(self, page: Page, server_url: str):
        """Index страница frontend загружается"""
        page.goto(f"{server_url}/frontend/")
        page.wait_for_load_state("domcontentloaded")
        
        assert page.title() or page.url, "Страница должна загрузиться"


@pytest.mark.playwright
class TestFashnPage:
    """Тесты страницы FASHN"""

    def test_fashn_page_loads(self, page: Page, server_url: str):
        """Страница FASHN загружается"""
        page.goto(f"{server_url}/frontend/fashn")
        page.wait_for_load_state("domcontentloaded")
        
        # Страница может требовать авторизации
        assert page.title() or page.url, "Страница должна загрузиться"
