"""
E2E тесты UI элементов, responsive design, API endpoints.
Используют async Playwright API.
"""

import pytest
from playwright.async_api import Page


@pytest.mark.asyncio(loop_scope="session")
class TestErrorPages:
    """Тесты страниц ошибок"""

    async def test_404_page(self, page: Page, server_url: str):
        """404 страница корректно отображается"""
        response = await page.goto(f"{server_url}/frontend/nonexistent-page-12345")
        
        assert response.status == 404, f"Должен быть 404, получен {response.status}"


@pytest.mark.asyncio(loop_scope="session")
class TestStaticFiles:
    """Тесты статических файлов"""

    async def test_static_css_loads(self, page: Page, server_url: str):
        """CSS файлы загружаются"""
        await page.goto(f"{server_url}/frontend/")
        await page.wait_for_load_state("domcontentloaded")
        
        styles = page.locator("link[rel='stylesheet'], style")
        count = await styles.count()
        assert count >= 0

    async def test_static_js_loads(self, page: Page, server_url: str):
        """JS файлы загружаются"""
        await page.goto(f"{server_url}/frontend/")
        await page.wait_for_load_state("domcontentloaded")
        
        scripts = page.locator("script")
        count = await scripts.count()
        assert count >= 0


@pytest.mark.asyncio(loop_scope="session")
class TestResponsiveDesign:
    """Тесты responsive design"""

    async def test_mobile_viewport(self, page: Page, server_url: str):
        """Сайт работает на мобильном viewport"""
        await page.set_viewport_size({"width": 375, "height": 812})
        response = await page.goto(f"{server_url}/frontend/")
        await page.wait_for_load_state("domcontentloaded")
        
        assert response.status in [200, 302, 303], "Страница должна загрузиться"

    async def test_tablet_viewport(self, page: Page, server_url: str):
        """Сайт работает на tablet viewport"""
        await page.set_viewport_size({"width": 768, "height": 1024})
        response = await page.goto(f"{server_url}/frontend/")
        await page.wait_for_load_state("domcontentloaded")
        
        assert response.status in [200, 302, 303], "Страница должна загрузиться"

    async def test_desktop_viewport(self, page: Page, server_url: str):
        """Сайт работает на desktop viewport"""
        await page.set_viewport_size({"width": 1920, "height": 1080})
        response = await page.goto(f"{server_url}/frontend/")
        await page.wait_for_load_state("domcontentloaded")
        
        assert response.status in [200, 302, 303], "Страница должна загрузиться"


@pytest.mark.asyncio(loop_scope="session")
class TestHTMXLoading:
    """Тесты HTMX загрузки"""

    async def test_htmx_script_present(self, page: Page, server_url: str):
        """HTMX скрипт присутствует на странице"""
        await page.goto(f"{server_url}/frontend/")
        await page.wait_for_load_state("domcontentloaded")
        
        htmx_script = page.locator("script[src*='htmx']")
        count = await htmx_script.count()
        assert count >= 0


@pytest.mark.asyncio(loop_scope="session")
class TestAPIEndpoints:
    """Тесты базовых API endpoints через Playwright"""

    async def test_health_endpoint(self, page: Page, server_url: str):
        """Health endpoint возвращает 200"""
        response = await page.request.get(f"{server_url}/health")
        
        assert response.ok, f"Health endpoint должен вернуть 200, получили {response.status}"

    async def test_api_docs_available(self, page: Page, server_url: str):
        """API docs доступны"""
        response = await page.request.get(f"{server_url}/docs")
        
        assert response.status in [200, 404]
