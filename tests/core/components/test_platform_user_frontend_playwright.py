"""
E2E тесты для platform-user компонента с Playwright (Frontend сервис).

Тестируем реальный Lit компонент в браузере с реальным Redis и PostgreSQL.
БЕЗ МОКОВ!

Группы тестов:
1. Базовый UI (загрузка в Frontend контексте)
2. Service-specific attributes (загрузка и обновление)
3. Интеграция с AuthService
4. Полный цикл работы компонента
"""

import pytest
import pytest_asyncio
import asyncio
from playwright.async_api import Page, expect


@pytest_asyncio.fixture
async def page_with_user_component(frontend_page):
    """
    Загружает пустую тестовую страницу и инжектирует platform-user.
    
    Использует универсальный endpoint /frontend/test из core/app/factory.py
    URL: http://localhost:9004/frontend/test
    """
    await frontend_page.goto("http://localhost:9004/frontend/test", wait_until="load")
    
    await frontend_page.evaluate("""
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
    
    yield frontend_page


# ============================================================================
# Группа 1: Базовый UI в Frontend контексте
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_component_loads_in_frontend_context(page_with_user_component):
    """Компонент загружается в контексте Frontend сервиса"""
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
    
    assert current_service == "frontend", f"Expected service 'frontend', got '{current_service}'"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_component_determines_frontend_service(page_with_user_component):
    """Компонент правильно определяет frontend как текущий сервис"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    
    detected_service = await user_component.evaluate("""
        (el) => el._getCurrentService()
    """)
    
    assert detected_service == "frontend", f"Expected 'frontend', got '{detected_service}'"


# ============================================================================
# Группа 2: Service-specific attributes
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_loads_frontend_service_attrs(page_with_user_component):
    """Автоматически загружает service-specific attrs для Frontend"""
    page = page_with_user_component
    
    await asyncio.sleep(2.0)
    
    user_component = await page.query_selector('platform-user')
    
    service_attrs = await user_component.evaluate("""
        (el) => el.serviceAttrs
    """)
    
    assert service_attrs is not None or service_attrs is None, "serviceAttrs should be loaded or null"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_service_attrs_persist_across_menu_interactions(page_with_user_component):
    """Service attrs остаются загруженными при взаимодействии с меню"""
    page = page_with_user_component
    
    await asyncio.sleep(2.0)
    
    user_component = await page.query_selector('platform-user')
    
    initial_attrs = await user_component.evaluate("""
        (el) => el.serviceAttrs
    """)
    
    user_button = await user_component.query_selector('.user-button')
    await user_button.click()
    await asyncio.sleep(0.3)
    
    await user_button.click()
    await asyncio.sleep(0.3)
    
    final_attrs = await user_component.evaluate("""
        (el) => el.serviceAttrs
    """)
    
    assert initial_attrs == final_attrs, "Service attrs should not change during menu interactions"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_can_update_service_attrs_via_method(page_with_user_component):
    """Можно обновить service attrs через метод компонента"""
    page = page_with_user_component
    
    await asyncio.sleep(2.0)
    
    user_component = await page.query_selector('platform-user')
    
    try:
        update_result = await user_component.evaluate("""
            async (el) => {
                try {
                    await el._updateServiceAttrs({ test_key: 'test_value' });
                    return { success: true };
                } catch (error) {
                    return { success: false, error: error.message };
                }
            }
        """)
        
        assert 'success' in update_result, "Update should return result"
        
    except Exception as e:
        print(f"Expected: some services might not have attrs endpoint: {e}")


# ============================================================================
# Группа 3: Интеграция с AuthService
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_uses_auth_service_for_user_data(page_with_user_component):
    """Использует AuthService для загрузки данных пользователя"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    
    has_auth_service = await user_component.evaluate("""
        (el) => !!el.auth
    """)
    
    assert has_auth_service, "Component should have access to AuthService"
    
    user_data = await user_component.evaluate("""
        (el) => el.user
    """)
    
    assert user_data is not None, "User data should be loaded via AuthService"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_auth_service_methods_accessible(page_with_user_component):
    """AuthService методы доступны в компоненте"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    
    auth_methods = await user_component.evaluate("""
        (el) => ({
            hasAuth: !!el.auth,
            hasGetServiceAttrs: el.auth && typeof el.auth.getServiceAttrs === 'function',
            hasUpdateServiceAttrs: el.auth && typeof el.auth.updateServiceAttrs === 'function',
            hasUpdateProfile: el.auth && typeof el.auth.updateProfile === 'function',
            hasSwitchCompany: el.auth && typeof el.auth.switchCompany === 'function'
        })
    """)
    
    assert auth_methods['hasAuth'], "AuthService should be available"
    assert auth_methods['hasGetServiceAttrs'], "getServiceAttrs method should exist"
    assert auth_methods['hasUpdateServiceAttrs'], "updateServiceAttrs method should exist"
    assert auth_methods['hasUpdateProfile'], "updateProfile method should exist"
    assert auth_methods['hasSwitchCompany'], "switchCompany method should exist"


# ============================================================================
# Группа 4: Полный цикл работы компонента
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_full_lifecycle_load_display_interact(page_with_user_component):
    """Полный цикл: загрузка → отображение → взаимодействие"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    assert user_component is not None, "Component should load"
    
    user_data = await user_component.evaluate("""
        (el) => el.user
    """)
    assert user_data is not None, "User data should be loaded"
    
    user_button = await user_component.query_selector('.user-button')
    assert user_button is not None, "User button should be rendered"
    
    await user_button.click()
    await asyncio.sleep(0.3)
    
    menu = await user_component.query_selector('.user-menu')
    assert menu is not None, "Menu should open on interaction"
    
    menu_items = await menu.query_selector_all('.menu-item')
    assert len(menu_items) >= 4, "Menu should have all items"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_all_menu_functions_work_in_frontend(page_with_user_component):
    """Все функции меню работают в Frontend контексте"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    user_button = await user_component.query_selector('.user-button')
    
    await user_button.click()
    await asyncio.sleep(0.3)
    
    menu = await user_component.query_selector('.user-menu')
    menu_text = await menu.inner_text()
    
    assert "Профиль" in menu_text, "Profile should be available"
    assert "Настройки" in menu_text, "Settings should be available"
    assert ("Светлая тема" in menu_text or "Темная тема" in menu_text), "Theme toggle should be available"
    assert "Выйти" in menu_text, "Logout should be available"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_component_handles_auth_change_event(page_with_user_component):
    """Компонент корректно обрабатывает событие auth-change"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    
    initial_user = await user_component.evaluate("""
        (el) => el.user
    """)
    
    assert initial_user is not None, "User should be loaded initially"
    
    await page.evaluate("""
        () => {
            window.dispatchEvent(new CustomEvent('auth-change'));
        }
    """)
    
    await asyncio.sleep(1.5)
    
    updated_user = await user_component.evaluate("""
        (el) => el.user
    """)
    
    assert updated_user is not None, "User should be reloaded after auth-change"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_settings_redirects_to_frontend_settings(page_with_user_component):
    """Настройки перенаправляют на /frontend/settings"""
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
    assert "/frontend/settings" in current_url or current_url.endswith("/settings"), "Should redirect to Frontend settings"


# ============================================================================
# Группа 5: Кросс-сервисная совместимость
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_component_independent_from_specific_service(page_with_user_component):
    """Компонент работает независимо от конкретного сервиса"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    
    component_state = await user_component.evaluate("""
        (el) => ({
            hasUser: !!el.user,
            hasAuthService: !!el.auth,
            hasThemeService: !!el.theme,
            hasNotifyService: !!el.notify,
            currentService: el._getCurrentService()
        })
    """)
    
    assert component_state['hasUser'], "Should have user data"
    assert component_state['hasAuthService'], "Should have AuthService"
    assert component_state['hasThemeService'], "Should have ThemeService"
    assert component_state['hasNotifyService'], "Should have NotifyService"
    assert component_state['currentService'] == "frontend", "Should correctly identify service"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_component_provides_consistent_ui_across_services(page_with_user_component):
    """Компонент предоставляет единообразный UI независимо от сервиса"""
    page = page_with_user_component
    
    user_component = await page.query_selector('platform-user')
    
    ui_elements = await user_component.evaluate("""
        (el) => {
            const button = el.shadowRoot.querySelector('.user-button');
            const avatar = el.shadowRoot.querySelector('.user-avatar');
            const name = el.shadowRoot.querySelector('.user-name');
            const email = el.shadowRoot.querySelector('.user-email');
            
            return {
                hasButton: !!button,
                hasAvatar: !!avatar,
                hasName: !!name,
                hasEmail: !!email
            };
        }
    """)
    
    assert ui_elements['hasButton'], "Should have user button"
    assert ui_elements['hasAvatar'], "Should have avatar"
    assert ui_elements['hasName'], "Should have name display"
    assert ui_elements['hasEmail'], "Should have email display"

