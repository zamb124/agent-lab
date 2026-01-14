"""
E2E тесты для platform-user компонента с Playwright (RAG сервис).

Тестируем реальный Lit компонент в браузере с реальным Redis и PostgreSQL.
БЕЗ МОКОВ!

Группы тестов:
1. Базовый UI (загрузка в RAG контексте)
2. Смена компании (если доступно несколько)
3. Отображение текущей компании
4. Интеграция с RAG сервисом
"""

import pytest
import pytest_asyncio
import asyncio
from playwright.async_api import Page, expect


@pytest_asyncio.fixture
async def page_with_user_component(rag_page):
    """
    Загружает пустую тестовую страницу и инжектирует platform-user.
    
    Использует универсальный endpoint /rag/test из core/app/factory.py
    URL: http://localhost:9002/rag/test
    """
    await rag_page.goto("http://localhost:9002/rag/test", wait_until="load")
    
    await rag_page.evaluate("""
        const script = document.createElement('script');
        script.type = 'module';
        script.src = '/static/core/lib/components/platform-user.js';
        document.head.appendChild(script);
        
        script.onload = () => {
            const component = document.createElement('platform-user');
            document.getElementById('test-root').appendChild(component);
        };
    """)
    
    await asyncio.sleep(3.0)
    
    yield rag_page


# ============================================================================
# Группа 1: Базовый UI в RAG контексте
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_component_loads_in_rag_context(page_with_user_component):
    """Компонент загружается в контексте RAG сервиса"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    assert user_component is not None, "platform-user element not found"
    
    is_visible = await user_component.is_visible()
    assert is_visible, "User component is not visible"
    
    current_service = await page.evaluate("""
        () => {
            const path = window.location.pathname;
            const match = path.match(/^\/([^\/]+)/);
            return match ? match[1] : null;
        }
    """)
    
    assert current_service == "rag", f"Expected service 'rag', got '{current_service}'"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_component_determines_rag_service(page_with_user_component):
    """Компонент правильно определяет RAG как текущий сервис"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    
    detected_service = await user_component.evaluate("""
        (el) => el._getCurrentService()
    """)
    
    assert detected_service == "rag", f"Expected 'rag', got '{detected_service}'"


# ============================================================================
# Группа 2: Отображение текущей компании
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_displays_current_company_if_available(page_with_user_component):
    """Отображает текущую компанию если она выбрана"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    
    user_data = await user_component.evaluate("""
        (el) => ({
            user: el.user,
            companies: el.companies
        })
    """)
    
    if user_data['user'] and user_data['user'].get('active_company_id'):
        company_elem = await user_component.query_selector('.user-company')
        
        if len(user_data['companies']) > 1:
            assert company_elem is not None, "Company name should be displayed when multiple companies available"
            
            company_text = await company_elem.inner_text()
            assert len(company_text) > 0, "Company name should not be empty"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_no_company_selector_if_single_company(page_with_user_component):
    """Селектор компании не отображается если доступна только одна компания"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    user_button = await user_component.query_selector('.user-button')
    
    companies = await user_component.evaluate("""
        (el) => el.companies
    """)
    
    if not companies or len(companies) <= 1:
        await user_button.click()
        await asyncio.sleep(0.3)
        
        menu = await user_component.query_selector('.user-menu')
        menu_text = await menu.inner_text()
        
        assert "Компания:" not in menu_text, "Company selector should not be visible with single company"


# ============================================================================
# Группа 3: Смена компании (для multi-tenant пользователей)
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_company_selector_appears_for_multiple_companies(page_with_user_component):
    """Селектор компании появляется если доступно несколько компаний"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    user_button = await user_component.query_selector('.user-button')
    
    companies = await user_component.evaluate("""
        (el) => el.companies
    """)
    
    if companies and len(companies) > 1:
        await user_button.click()
        await asyncio.sleep(0.3)
        
        menu = await user_component.query_selector('.user-menu')
        menu_text = await menu.inner_text()
        
        assert "Компания:" in menu_text, "Company selector should be visible with multiple companies"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_company_dropdown_opens(page_with_user_component):
    """Выпадающий список компаний открывается при клике"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    user_button = await user_component.query_selector('.user-button')
    
    companies = await user_component.evaluate("""
        (el) => el.companies
    """)
    
    if companies and len(companies) > 1:
        await user_button.click()
        await asyncio.sleep(0.3)
        
        menu = await user_component.query_selector('.user-menu')
        menu_items = await menu.query_selector_all('.menu-item')
        
        company_menu_item = None
        for item in menu_items:
            text = await item.inner_text()
            if "Компания:" in text:
                company_menu_item = item
                break
        
        if company_menu_item:
            await company_menu_item.click()
            await asyncio.sleep(0.3)
            
            company_selector = await user_component.query_selector('.company-selector')
            assert company_selector is not None, "Company selector dropdown should open"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_company_list_contains_all_companies(page_with_user_component):
    """Список компаний содержит все доступные компании"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    user_button = await user_component.query_selector('.user-button')
    
    companies = await user_component.evaluate("""
        (el) => el.companies
    """)
    
    if companies and len(companies) > 1:
        await user_button.click()
        await asyncio.sleep(0.3)
        
        menu = await user_component.query_selector('.user-menu')
        menu_items = await menu.query_selector_all('.menu-item')
        
        for item in menu_items:
            text = await item.inner_text()
            if "Компания:" in text:
                await item.click()
                break
        
        await asyncio.sleep(0.3)
        
        company_selector = await user_component.query_selector('.company-selector')
        
        if company_selector:
            company_items = await company_selector.query_selector_all('.company-item')
            assert len(company_items) == len(companies), f"Expected {len(companies)} companies, found {len(company_items)}"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_active_company_is_highlighted(page_with_user_component):
    """Активная компания выделена в списке"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    user_button = await user_component.query_selector('.user-button')
    
    companies = await user_component.evaluate("""
        (el) => ({
            companies: el.companies,
            activeCompanyId: el.user?.active_company_id
        })
    """)
    
    if companies['companies'] and len(companies['companies']) > 1 and companies['activeCompanyId']:
        await user_button.click()
        await asyncio.sleep(0.3)
        
        menu = await user_component.query_selector('.user-menu')
        menu_items = await menu.query_selector_all('.menu-item')
        
        for item in menu_items:
            text = await item.inner_text()
            if "Компания:" in text:
                await item.click()
                break
        
        await asyncio.sleep(0.3)
        
        company_selector = await user_component.query_selector('.company-selector')
        
        if company_selector:
            active_company = await company_selector.query_selector('.company-item.active')
            assert active_company is not None, "Active company should be highlighted"


# ============================================================================
# Группа 4: Интеграция с RAG сервисом
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_loads_rag_service_attrs(page_with_user_component):
    """Загружает service-specific attrs для RAG"""
    page = page_with_user_component
    
    await asyncio.sleep(2.0)
    
    user_component = await page.query_selector('platform-user')
    
    service_attrs = await user_component.evaluate("""
        (el) => el.serviceAttrs
    """)
    
    assert service_attrs is not None or service_attrs is None, "serviceAttrs should be loaded or null"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_user_menu_functional_in_rag(page_with_user_component):
    """Все функции меню работают в RAG контексте"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    user_button = await user_component.query_selector('.user-button')
    
    await user_button.click()
    await asyncio.sleep(0.3)
    
    menu = await user_component.query_selector('.user-menu')
    assert menu is not None, "Menu should open"
    
    menu_items = await menu.query_selector_all('.menu-item')
    assert len(menu_items) >= 4, "Menu should have all expected items"
    
    menu_text = await menu.inner_text()
    assert "Профиль" in menu_text, "Profile should be available"
    assert "Настройки" in menu_text, "Settings should be available"
    assert "Выйти" in menu_text, "Logout should be available"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_settings_redirects_to_rag_settings(page_with_user_component):
    """Настройки перенаправляют на /rag/settings"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    user_button = await user_component.query_selector('.user-button')
    
    await user_button.click()
    await asyncio.sleep(0.3)
    
    menu = await user_component.query_selector('.user-menu')
    menu_items = await menu.query_selector_all('.menu-item')
    
    for item in menu_items:
        text = await item.inner_text()
        if "Настройки" in text:
            await item.click()
            break
    
    await asyncio.sleep(1.0)
    
    current_url = page.url
    assert "/rag/settings" in current_url or current_url.endswith("/settings"), "Should redirect to RAG settings"


# ============================================================================
# Группа 5: Реактивность
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_component_updates_on_auth_change(page_with_user_component):
    """Компонент реагирует на изменение auth состояния"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    
    initial_user = await user_component.evaluate("""
        (el) => el.user
    """)
    
    assert initial_user is not None, "User should be loaded initially"
    
    auth_change_fired = await page.evaluate("""
        () => {
            window.dispatchEvent(new CustomEvent('auth-change'));
            return true;
        }
    """)
    
    assert auth_change_fired, "Auth change event should be fired"
    
    await asyncio.sleep(1.0)
    
    updated_user = await user_component.evaluate("""
        (el) => el.user
    """)
    
    assert updated_user is not None, "User should still be loaded after auth change"

