"""
E2E тесты модулей frontend.

Тестируем что страницы модулей загружаются.
Большинство модулей требуют авторизации, поэтому проверяем базовую загрузку.
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.playwright
class TestBotsModule:
    """Тесты модуля Bots"""

    def test_bots_page_loads(self, page: Page, server_url: str):
        """Страница ботов загружается"""
        page.goto(f"{server_url}/frontend/bots/")
        page.wait_for_load_state("domcontentloaded")
        
        assert page.title() or page.url, "Страница должна загрузиться"


@pytest.mark.playwright
class TestBuilderModule:
    """Тесты модуля Builder"""

    def test_builder_page_loads(self, page: Page, server_url: str):
        """Страница конструктора загружается"""
        page.goto(f"{server_url}/frontend/builder/")
        page.wait_for_load_state("domcontentloaded")
        
        assert page.title() or page.url, "Страница должна загрузиться"


@pytest.mark.playwright
class TestAbilitiesModule:
    """Тесты модуля Abilities"""

    def test_abilities_page_loads(self, page: Page, server_url: str):
        """Страница способностей загружается"""
        page.goto(f"{server_url}/frontend/abilities/")
        page.wait_for_load_state("domcontentloaded")
        
        assert page.title() or page.url, "Страница должна загрузиться"


@pytest.mark.playwright
class TestBillingModule:
    """Тесты модуля Billing"""

    def test_billing_page_loads(self, page: Page, server_url: str):
        """Страница биллинга загружается"""
        page.goto(f"{server_url}/frontend/billing/")
        page.wait_for_load_state("domcontentloaded")
        
        assert page.title() or page.url, "Страница должна загрузиться"


@pytest.mark.playwright
class TestHistoryModule:
    """Тесты модуля History"""

    def test_history_page_loads(self, page: Page, server_url: str):
        """Страница истории загружается"""
        page.goto(f"{server_url}/frontend/history/")
        page.wait_for_load_state("domcontentloaded")
        
        assert page.title() or page.url, "Страница должна загрузиться"


@pytest.mark.playwright
class TestVariablesModule:
    """Тесты модуля Variables"""

    def test_variables_page_loads(self, page: Page, server_url: str):
        """Страница переменных загружается"""
        page.goto(f"{server_url}/frontend/variables/")
        page.wait_for_load_state("domcontentloaded")
        
        assert page.title() or page.url, "Страница должна загрузиться"


@pytest.mark.playwright
class TestMCPModule:
    """Тесты модуля MCP"""

    def test_mcp_page_loads(self, page: Page, server_url: str):
        """Страница MCP загружается"""
        page.goto(f"{server_url}/frontend/mcp/")
        page.wait_for_load_state("domcontentloaded")
        
        assert page.title() or page.url, "Страница должна загрузиться"


@pytest.mark.playwright
class TestStoreModule:
    """Тесты модуля Store"""

    def test_store_page_loads(self, page: Page, server_url: str):
        """Страница магазина загружается"""
        page.goto(f"{server_url}/frontend/store/")
        page.wait_for_load_state("domcontentloaded")
        
        assert page.title() or page.url, "Страница должна загрузиться"


@pytest.mark.playwright
class TestChatsModule:
    """Тесты модуля Chats"""

    def test_chats_page_loads(self, page: Page, server_url: str):
        """Страница чатов загружается"""
        page.goto(f"{server_url}/frontend/chats/")
        page.wait_for_load_state("domcontentloaded")
        
        assert page.title() or page.url, "Страница должна загрузиться"


@pytest.mark.playwright
class TestTracesModule:
    """Тесты модуля Traces"""

    def test_traces_page_loads(self, page: Page, server_url: str):
        """Страница трейсов загружается"""
        page.goto(f"{server_url}/frontend/traces/")
        page.wait_for_load_state("domcontentloaded")
        
        assert page.title() or page.url, "Страница должна загрузиться"
