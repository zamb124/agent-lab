"""
Playwright фикстуры для E2E UI тестов.

Предоставляет браузерные контексты с авторизацией для разных сервисов.
"""

import pytest_asyncio
from playwright.async_api import Browser, BrowserContext, Page


@pytest_asyncio.fixture
async def authenticated_browser_context(
    browser: Browser,
    auth_token_system: str,
    system_user_id: str,
) -> BrowserContext:
    """
    Браузерный контекст с авторизационными cookies.
    
    Подходит для тестирования любого сервиса (CRM, Frontend, Agents, RAG).
    Cookies устанавливаются для localhost, работают на всех портах.
    
    Cookies:
    - auth_token: JWT токен с user_id и company_id
    - session_id: user_id для быстрого доступа
    - company_id: активная компания (для CRM)
    """
    context = await browser.new_context()
    
    await context.add_cookies([
        {
            "name": "auth_token",
            "value": auth_token_system,
            "domain": "localhost",
            "path": "/",
        },
        {
            "name": "session_id", 
            "value": system_user_id,
            "domain": "localhost",
            "path": "/",
        },
        {
            "name": "company_id",
            "value": "system",
            "domain": "localhost",
            "path": "/",
        }
    ])
    
    yield context
    
    await context.close()


@pytest_asyncio.fixture
async def authenticated_page(authenticated_browser_context: BrowserContext) -> Page:
    """
    Страница браузера с авторизацией.
    
    Готова к использованию для UI тестов любого сервиса.
    """
    page = await authenticated_browser_context.new_page()
    
    yield page
    
    await page.close()


@pytest_asyncio.fixture
async def crm_page(authenticated_page: Page, crm_service) -> Page:
    """
    Страница CRM сервиса с авторизацией.
    
    НЕ делает goto - тест сам решает куда переходить.
    Cookies уже установлены через authenticated_page.
    
    Рекомендуемый URL для тестов: http://localhost:9003/crm/test
    WebSocket: ws://localhost:9003/crm/ws/notifications
    """
    yield authenticated_page


@pytest_asyncio.fixture
async def agents_page(authenticated_page: Page, agents_service) -> Page:
    """
    Страница Agents сервиса с авторизацией.
    
    НЕ делает goto - тест сам решает куда переходить.
    Cookies уже установлены через authenticated_page.
    
    Рекомендуемый URL для тестов: http://localhost:9001/agents/test
    WebSocket: ws://localhost:9001/agents/ws/notifications
    """
    yield authenticated_page


@pytest_asyncio.fixture
async def rag_page(authenticated_page: Page, rag_service) -> Page:
    """
    Страница RAG сервиса с авторизацией.
    
    НЕ делает goto - тест сам решает куда переходить.
    Cookies уже установлены через authenticated_page.
    
    Рекомендуемый URL для тестов: http://localhost:9002/rag/test
    WebSocket: ws://localhost:9002/rag/ws/notifications
    """
    yield authenticated_page


@pytest_asyncio.fixture
async def frontend_page(authenticated_page: Page, frontend_service) -> Page:
    """
    Страница Frontend сервиса с авторизацией.
    
    НЕ делает goto - тест сам решает куда переходить.
    Cookies уже установлены через authenticated_page.
    
    Рекомендуемый URL для тестов: http://localhost:9004/frontend/test
    WebSocket: ws://localhost:9004/frontend/ws/notifications
    """
    yield authenticated_page

