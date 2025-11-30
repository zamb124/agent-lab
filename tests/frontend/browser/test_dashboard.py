"""
E2E тесты dashboard страниц.
Используют async Playwright API.
"""

import pytest
from playwright.async_api import Page


@pytest.mark.asyncio(loop_scope="session")
class TestDashboardPages:
    """Тесты страниц dashboard"""

    async def test_index_responds(self, page: Page, server_url: str):
        """Главная страница frontend отвечает"""
        response = await page.goto(f"{server_url}/frontend/")
        await page.wait_for_load_state("domcontentloaded")
        
        assert response.status == 200, f"Ожидался 200, получен {response.status}"

    async def test_dashboard_responds(self, page: Page, server_url: str):
        """Dashboard страница отвечает"""
        response = await page.goto(f"{server_url}/frontend/dashboard")
        await page.wait_for_load_state("domcontentloaded")
        
        assert response.status == 200, f"Ожидался 200, получен {response.status}"

    async def test_fashn_page_responds(self, page: Page, server_url: str):
        """Fashn страница отвечает"""
        response = await page.goto(f"{server_url}/frontend/fashn")
        await page.wait_for_load_state("domcontentloaded")
        
        assert response.status == 200, f"Ожидался 200, получен {response.status}"
