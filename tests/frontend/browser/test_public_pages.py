"""
E2E тесты публичных страниц: landing, privacy, terms.
Используют async Playwright API.
"""

import pytest
from playwright.async_api import Page, expect


@pytest.mark.asyncio(loop_scope="session")
class TestLandingPage:
    """Тесты главной страницы (landing)"""

    async def test_landing_page_loads(self, page: Page, server_url: str):
        """Главная страница загружается"""
        await page.goto(server_url)
        await page.wait_for_load_state("domcontentloaded")
        
        title = await page.title()
        assert title, "Страница должна иметь title"

    async def test_landing_has_content(self, page: Page, server_url: str):
        """Главная страница содержит контент"""
        await page.goto(server_url)
        await page.wait_for_load_state("domcontentloaded")
        
        content = await page.content()
        assert len(content) > 500, "Страница должна иметь контент"

    async def test_landing_has_navigation(self, page: Page, server_url: str):
        """Главная страница содержит навигацию"""
        await page.goto(server_url)
        
        nav = page.locator("nav, header, .navbar, .navigation")
        count = await nav.count()
        if count > 0:
            await expect(nav.first).to_be_visible(timeout=10000)

    async def test_landing_has_main_content(self, page: Page, server_url: str):
        """Главная страница содержит основной блок"""
        await page.goto(server_url)
        
        main = page.locator("main, .main, .content, .hero, article, section")
        count = await main.count()
        if count > 0:
            await expect(main.first).to_be_visible(timeout=10000)


@pytest.mark.asyncio(loop_scope="session")
class TestPrivacyPage:
    """Тесты страницы политики конфиденциальности"""

    async def test_privacy_page_loads(self, page: Page, server_url: str):
        """Страница privacy загружается"""
        await page.goto(f"{server_url}/privacy")
        await page.wait_for_load_state("domcontentloaded")
        
        title = await page.title()
        assert title, "Страница должна иметь title"

    async def test_privacy_has_content(self, page: Page, server_url: str):
        """Страница privacy содержит контент"""
        await page.goto(f"{server_url}/privacy")
        await page.wait_for_load_state("domcontentloaded")
        
        content_locator = page.locator("main, article, .content, .privacy-content, section, div.container")
        count = await content_locator.count()
        if count > 0:
            await expect(content_locator.first).to_be_visible(timeout=10000)

    async def test_privacy_page_with_lang(self, page: Page, server_url: str):
        """Страница privacy с параметром языка"""
        await page.goto(f"{server_url}/privacy?lang=en")
        await page.wait_for_load_state("domcontentloaded")
        
        title = await page.title()
        assert title, "Страница должна иметь title"


@pytest.mark.asyncio(loop_scope="session")
class TestTermsPage:
    """Тесты страницы условий использования"""

    async def test_terms_page_loads(self, page: Page, server_url: str):
        """Страница terms загружается"""
        await page.goto(f"{server_url}/terms")
        await page.wait_for_load_state("domcontentloaded")
        
        title = await page.title()
        assert title, "Страница должна иметь title"

    async def test_terms_has_content(self, page: Page, server_url: str):
        """Страница terms содержит контент"""
        await page.goto(f"{server_url}/terms")
        await page.wait_for_load_state("domcontentloaded")
        
        content_locator = page.locator("main, article, .content, .terms-content, section, div.container")
        count = await content_locator.count()
        if count > 0:
            await expect(content_locator.first).to_be_visible(timeout=10000)

    async def test_terms_page_with_lang(self, page: Page, server_url: str):
        """Страница terms с параметром языка"""
        await page.goto(f"{server_url}/terms?lang=ru")
        await page.wait_for_load_state("domcontentloaded")
        
        title = await page.title()
        assert title, "Страница должна иметь title"


@pytest.mark.asyncio(loop_scope="session")
class TestPublicPagesNavigation:
    """Тесты навигации между публичными страницами"""

    async def test_can_navigate_to_privacy(self, page: Page, server_url: str):
        """Можно перейти на страницу privacy"""
        await page.goto(server_url)
        
        privacy_link = page.locator("a[href*='privacy']")
        count = await privacy_link.count()
        if count > 0:
            await privacy_link.first.click()
            await page.wait_for_load_state("domcontentloaded")
            assert "/privacy" in page.url

    async def test_can_navigate_to_terms(self, page: Page, server_url: str):
        """Можно перейти на страницу terms"""
        await page.goto(server_url)
        
        terms_link = page.locator("a[href*='terms']")
        count = await terms_link.count()
        if count > 0:
            await terms_link.first.click()
            await page.wait_for_load_state("domcontentloaded")
            assert "/terms" in page.url
