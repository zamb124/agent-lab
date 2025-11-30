"""
E2E тесты страниц авторизации.
Используют async Playwright API.
"""

import pytest
from playwright.async_api import Page


@pytest.mark.asyncio(loop_scope="session")
class TestAuthPage:
    """Тесты страницы авторизации"""

    async def test_auth_page_loads(self, page: Page, server_url: str):
        """Страница авторизации загружается"""
        response = await page.goto(f"{server_url}/frontend/auth")
        await page.wait_for_load_state("domcontentloaded")
        
        assert response.status in [200, 302, 303], f"Ожидался успешный ответ, получен {response.status}"

    async def test_auth_page_has_content(self, page: Page, server_url: str):
        """Страница авторизации содержит контент"""
        await page.goto(f"{server_url}/frontend/auth")
        await page.wait_for_load_state("domcontentloaded")
        
        content = await page.content()
        assert len(content) > 100, "Страница должна иметь контент"


@pytest.mark.asyncio(loop_scope="session")
class TestSelectCompanyPage:
    """Тесты страницы выбора компании"""

    async def test_select_company_loads(self, page: Page, server_url: str):
        """Страница выбора компании загружается"""
        response = await page.goto(f"{server_url}/frontend/select-company")
        await page.wait_for_load_state("domcontentloaded")
        
        assert response.status in [200, 302, 303], f"Ожидался ответ, получен {response.status}"


@pytest.mark.asyncio(loop_scope="session")
class TestCreateCompanyPage:
    """Тесты страницы создания компании"""

    async def test_create_company_page_loads(self, page: Page, server_url: str):
        """Страница создания компании загружается"""
        response = await page.goto(f"{server_url}/frontend/create-company")
        await page.wait_for_load_state("domcontentloaded")
        
        assert response.status in [200, 302, 303], f"Ожидался ответ, получен {response.status}"
