"""
E2E тесты модулей frontend.
Используют async Playwright API.
"""

import pytest
from playwright.async_api import Page


@pytest.mark.asyncio(loop_scope="session")
class TestBotsModule:
    """Тесты модуля bots"""

    async def test_bots_page_responds(self, page: Page, server_url: str):
        """Страница bots отвечает"""
        response = await page.goto(f"{server_url}/frontend/bots")
        await page.wait_for_load_state("domcontentloaded")
        
        assert response.status in [200, 302, 303], f"Сервер должен ответить, получен {response.status}"


@pytest.mark.asyncio(loop_scope="session")
class TestBuilderModule:
    """Тесты модуля builder"""

    async def test_builder_page_responds(self, page: Page, server_url: str):
        """Страница builder отвечает"""
        response = await page.goto(f"{server_url}/frontend/builder")
        await page.wait_for_load_state("domcontentloaded")
        
        assert response.status in [200, 302, 303], f"Сервер должен ответить, получен {response.status}"


@pytest.mark.asyncio(loop_scope="session")
class TestAbilitiesModule:
    """Тесты модуля abilities"""

    async def test_abilities_page_responds(self, page: Page, server_url: str):
        """Страница abilities отвечает"""
        response = await page.goto(f"{server_url}/frontend/abilities")
        await page.wait_for_load_state("domcontentloaded")
        
        assert response.status in [200, 302, 303], f"Сервер должен ответить, получен {response.status}"


@pytest.mark.asyncio(loop_scope="session")
class TestBillingModule:
    """Тесты модуля billing"""

    async def test_billing_page_responds(self, page: Page, server_url: str):
        """Страница billing отвечает"""
        response = await page.goto(f"{server_url}/frontend/billing")
        await page.wait_for_load_state("domcontentloaded")
        
        assert response.status in [200, 302, 303], f"Сервер должен ответить, получен {response.status}"


@pytest.mark.asyncio(loop_scope="session")
class TestHistoryModule:
    """Тесты модуля history"""

    async def test_history_page_responds(self, page: Page, server_url: str):
        """Страница history отвечает"""
        response = await page.goto(f"{server_url}/frontend/history")
        await page.wait_for_load_state("domcontentloaded")
        
        assert response.status in [200, 302, 303], f"Сервер должен ответить, получен {response.status}"


@pytest.mark.asyncio(loop_scope="session")
class TestVariablesModule:
    """Тесты модуля variables"""

    async def test_variables_page_responds(self, page: Page, server_url: str):
        """Страница variables отвечает"""
        response = await page.goto(f"{server_url}/frontend/variables")
        await page.wait_for_load_state("domcontentloaded")
        
        assert response.status in [200, 302, 303], f"Сервер должен ответить, получен {response.status}"


@pytest.mark.asyncio(loop_scope="session")
class TestMCPModule:
    """Тесты модуля MCP"""

    async def test_mcp_page_responds(self, page: Page, server_url: str):
        """Страница MCP отвечает"""
        response = await page.goto(f"{server_url}/frontend/mcp")
        await page.wait_for_load_state("domcontentloaded")
        
        assert response.status in [200, 302, 303], f"Сервер должен ответить, получен {response.status}"


@pytest.mark.asyncio(loop_scope="session")
class TestStoreModule:
    """Тесты модуля store"""

    async def test_store_page_responds(self, page: Page, server_url: str):
        """Страница store отвечает"""
        response = await page.goto(f"{server_url}/frontend/store")
        await page.wait_for_load_state("domcontentloaded")
        
        assert response.status in [200, 302, 303], f"Сервер должен ответить, получен {response.status}"


@pytest.mark.asyncio(loop_scope="session")
class TestChatsModule:
    """Тесты модуля chats"""

    async def test_chats_page_responds(self, page: Page, server_url: str):
        """Страница chats отвечает"""
        response = await page.goto(f"{server_url}/frontend/chats")
        await page.wait_for_load_state("domcontentloaded")
        
        assert response.status in [200, 302, 303], f"Сервер должен ответить, получен {response.status}"


@pytest.mark.asyncio(loop_scope="session")
class TestTracesModule:
    """Тесты модуля traces"""

    async def test_traces_page_responds(self, page: Page, server_url: str):
        """Страница traces отвечает"""
        response = await page.goto(f"{server_url}/frontend/traces")
        await page.wait_for_load_state("domcontentloaded")
        
        assert response.status in [200, 302, 303], f"Сервер должен ответить, получен {response.status}"
