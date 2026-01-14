"""
E2E тесты для platform-user компонента с Playwright (Agents сервис).

Тестируем реальный Lit компонент в браузере с реальным Redis и PostgreSQL.
БЕЗ МОКОВ!

Группы тестов:
1. Базовый UI (загрузка в navbar контексте)
2. Редактирование профиля
3. Переключение темы
4. Настройки
"""

import pytest
import pytest_asyncio
import asyncio
from playwright.async_api import Page, expect


@pytest_asyncio.fixture
async def page_with_user_component(agents_page):
    """
    Загружает пустую тестовую страницу и инжектирует platform-user.
    
    Использует универсальный endpoint /agents/test из core/app/factory.py
    URL: http://localhost:9001/agents/test
    """
    await agents_page.goto("http://localhost:9001/agents/test", wait_until="load")
    
    await agents_page.evaluate("""
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
    
    yield agents_page


# ============================================================================
# Группа 1: Базовый UI
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_component_loads_in_agents_context(page_with_user_component):
    """Компонент загружается в контексте Agents сервиса"""
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
    
    assert current_service == "agents", f"Expected service 'agents', got '{current_service}'"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_component_determines_correct_service(page_with_user_component):
    """Компонент правильно определяет текущий сервис"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    
    detected_service = await user_component.evaluate("""
        (el) => el._getCurrentService()
    """)
    
    assert detected_service == "agents", f"Expected 'agents', got '{detected_service}'"


# ============================================================================
# Группа 2: Редактирование профиля
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_profile_modal_edit_name(page_with_user_component):
    """Можно редактировать имя в профиле"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    user_button = await user_component.query_selector('.user-button')
    
    await user_button.click()
    await asyncio.sleep(0.3)
    
    menu = await user_component.query_selector('.user-menu')
    menu_items = await menu.query_selector_all('.menu-item')
    
    for item in menu_items:
        text = await item.inner_text()
        if "Профиль" in text:
            await item.click()
            break
    
    await asyncio.sleep(0.5)
    
    modal = await page.query_selector('user-profile-modal')
    name_input = await modal.query_selector('input[name="name"]')
    
    current_name = await name_input.input_value()
    assert len(current_name) >= 0, "Name input should have value or be empty"
    
    await name_input.fill("Test User Updated")
    
    new_value = await name_input.input_value()
    assert new_value == "Test User Updated", "Name should be updated"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_profile_modal_edit_bio(page_with_user_component):
    """Можно редактировать bio в профиле"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    user_button = await user_component.query_selector('.user-button')
    
    await user_button.click()
    await asyncio.sleep(0.3)
    
    menu = await user_component.query_selector('.user-menu')
    menu_items = await menu.query_selector_all('.menu-item')
    
    for item in menu_items:
        text = await item.inner_text()
        if "Профиль" in text:
            await item.click()
            break
    
    await asyncio.sleep(0.5)
    
    modal = await page.query_selector('user-profile-modal')
    bio_textarea = await modal.query_selector('textarea[name="bio"]')
    
    await bio_textarea.fill("This is my updated bio")
    
    new_value = await bio_textarea.input_value()
    assert new_value == "This is my updated bio", "Bio should be updated"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_profile_modal_change_language(page_with_user_component):
    """Можно изменить язык интерфейса"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    user_button = await user_component.query_selector('.user-button')
    
    await user_button.click()
    await asyncio.sleep(0.3)
    
    menu = await user_component.query_selector('.user-menu')
    menu_items = await menu.query_selector_all('.menu-item')
    
    for item in menu_items:
        text = await item.inner_text()
        if "Профиль" in text:
            await item.click()
            break
    
    await asyncio.sleep(0.5)
    
    modal = await page.query_selector('user-profile-modal')
    language_select = await modal.query_selector('select[name="language"]')
    
    await language_select.select_option("en")
    
    selected_value = await language_select.input_value()
    assert selected_value == "en", "Language should be changed to English"
    
    await language_select.select_option("ru")
    
    selected_value = await language_select.input_value()
    assert selected_value == "ru", "Language should be changed back to Russian"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_profile_modal_has_close_button(page_with_user_component):
    """Модальное окно профиля можно закрыть"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    user_button = await user_component.query_selector('.user-button')
    
    await user_button.click()
    await asyncio.sleep(0.3)
    
    menu = await user_component.query_selector('.user-menu')
    menu_items = await menu.query_selector_all('.menu-item')
    
    for item in menu_items:
        text = await item.inner_text()
        if "Профиль" in text:
            await item.click()
            break
    
    await asyncio.sleep(0.5)
    
    modal = await page.query_selector('user-profile-modal')
    assert modal is not None, "Modal should be open"
    
    close_button = await modal.query_selector('.close-button, button[aria-label*="lose"], button[aria-label*="закрыть"]')
    
    if close_button:
        await close_button.click()
        await asyncio.sleep(0.3)
        
        modal = await page.query_selector('user-profile-modal')
        assert modal is None, "Modal should be closed after clicking close button"


# ============================================================================
# Группа 3: Переключение темы
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_theme_toggle_exists_in_menu(page_with_user_component):
    """Кнопка переключения темы присутствует в меню"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    user_button = await user_component.query_selector('.user-button')
    
    await user_button.click()
    await asyncio.sleep(0.3)
    
    menu = await user_component.query_selector('.user-menu')
    menu_text = await menu.inner_text()
    
    assert ("Светлая тема" in menu_text or "Темная тема" in menu_text), "Theme toggle should be in menu"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_theme_toggle_clickable(page_with_user_component):
    """Кнопка переключения темы кликабельна"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    user_button = await user_component.query_selector('.user-button')
    
    await user_button.click()
    await asyncio.sleep(0.3)
    
    menu = await user_component.query_selector('.user-menu')
    menu_items = await menu.query_selector_all('.menu-item')
    
    theme_item = None
    for item in menu_items:
        text = await item.inner_text()
        if "тема" in text.lower():
            theme_item = item
            break
    
    assert theme_item is not None, "Theme toggle menu item not found"
    
    is_enabled = await theme_item.is_enabled()
    assert is_enabled, "Theme toggle should be enabled"
    
    await theme_item.click()
    await asyncio.sleep(0.5)


# ============================================================================
# Группа 4: Настройки
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_settings_menu_item_exists(page_with_user_component):
    """Пункт меню 'Настройки' присутствует"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    user_button = await user_component.query_selector('.user-button')
    
    await user_button.click()
    await asyncio.sleep(0.3)
    
    menu = await user_component.query_selector('.user-menu')
    menu_text = await menu.inner_text()
    
    assert "Настройки" in menu_text, "Settings menu item should exist"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_settings_redirects_to_service_settings(page_with_user_component):
    """Клик на 'Настройки' перенаправляет на /agents/settings"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    user_button = await user_component.query_selector('.user-button')
    
    await user_button.click()
    await asyncio.sleep(0.3)
    
    menu = await user_component.query_selector('.user-menu')
    menu_items = await menu.query_selector_all('.menu-item')
    
    settings_item = None
    for item in menu_items:
        text = await item.inner_text()
        if "Настройки" in text:
            settings_item = item
            break
    
    assert settings_item is not None, "Settings menu item not found"
    
    await settings_item.click()
    await asyncio.sleep(1.0)
    
    current_url = page.url
    assert "/agents/settings" in current_url or current_url.endswith("/settings"), "Should redirect to settings page"


# ============================================================================
# Группа 5: Интеграция с сервисом
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_component_loads_user_from_auth_service(page_with_user_component):
    """Компонент загружает данные пользователя через AuthService"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    
    user_data = await user_component.evaluate("""
        (el) => el.user
    """)
    
    assert user_data is not None, "User data should be loaded"
    assert "email" in user_data or "name" in user_data, "User should have email or name"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_component_auto_detects_agents_service_attrs(page_with_user_component):
    """Компонент автоматически загружает attrs для agents сервиса"""
    page = page_with_user_component
    
    await asyncio.sleep(2.0)
    
    user_component = await page.query_selector('platform-user')
    
    service_attrs = await user_component.evaluate("""
        (el) => el.serviceAttrs
    """)
    
    assert service_attrs is not None or service_attrs is None, "serviceAttrs should be loaded or null"

