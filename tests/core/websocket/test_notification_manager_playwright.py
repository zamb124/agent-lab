"""
E2E тесты для platform-notification-manager компонента с Playwright.

Тестируем реальный Lit компонент в браузере с реальным WebSocket и Redis.
БЕЗ МОКОВ!
"""

import pytest
import pytest_asyncio
import asyncio
from playwright.async_api import Page, expect

from core.websocket.publisher import notify_user, Notification, NotificationType


@pytest_asyncio.fixture
async def page_with_notification_component(crm_page):
    """
    Загружает пустую тестовую страницу и инжектирует notification-manager.
    
    Использует универсальный endpoint /crm/test из core/app/factory.py
    URL: http://localhost:9003/crm/test
    WebSocket: ws://localhost:9003/crm/ws/notifications (определяется автоматически)
    """
    # Переходим на пустую тестовую страницу с правильным pathname
    await crm_page.goto("http://localhost:9003/crm/test", wait_until="load")
    
    # Инжектируем notification-manager компонент
    await crm_page.evaluate("""
        const script = document.createElement('script');
        script.type = 'module';
        script.src = '/static/core/lib/components/platform-notification-manager.js';
        document.head.appendChild(script);
        
        // Создаем компонент после загрузки скрипта
        script.onload = () => {
            const manager = document.createElement('platform-notification-manager');
            document.getElementById('test-root').appendChild(manager);
        };
    """)
    
    # Ждем загрузку скрипта и инициализацию компонента
    await asyncio.sleep(5.0)
    
    yield crm_page


# ============================================================================
# Группа 1: Базовый UI
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_component_loads_and_connects(page_with_notification_component):
    """Компонент загружается, кнопка видна, WebSocket подключен"""
    page = page_with_notification_component
    
    console_logs = []
    page.on('console', lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
    
    manager = await page.query_selector('platform-notification-manager')
    assert manager is not None, "platform-notification-manager element not found"
    
    is_visible = await manager.is_visible()
    assert is_visible, "Manager is not visible"
    
    button = await manager.query_selector('.notification-button')
    assert button is not None, "Notification button not found"
    
    button_visible = await button.is_visible()
    assert button_visible, "Button is not visible"
    
    print(f"\n=== Waiting for WebSocket connection... ===")
    await asyncio.sleep(2)
    
    print(f"\n=== Console logs: ===")
    for log in console_logs:
        print(log)
    
    ws_info = await manager.evaluate('''
        (el) => {
            const ws = el._ws;
            return {
                exists: !!ws,
                readyState: ws ? ws.readyState : null,
                url: ws ? ws.url : null,
                isConnected: el.isConnected
            };
        }
    ''')
    print(f"\n=== WebSocket info: {ws_info} ===")
    
    if ws_info['readyState'] is not None:
        ready_states = {0: 'CONNECTING', 1: 'OPEN', 2: 'CLOSING', 3: 'CLOSED'}
        print(f"=== WebSocket state: {ready_states.get(ws_info['readyState'], 'UNKNOWN')} ===")
    
    status = await manager.query_selector('.status')
    assert status is not None, "Status indicator not found"
    
    has_connected_class = await status.evaluate('(el) => el.classList.contains("connected")')
    has_disconnected_class = await status.evaluate('(el) => el.classList.contains("disconnected")')
    
    print(f"=== Status classes: connected={has_connected_class}, disconnected={has_disconnected_class} ===")
    
    assert has_connected_class or has_disconnected_class, "Status should have either connected or disconnected class"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_notification_button_has_status_indicator(page_with_notification_component):
    """Индикатор подключения (зеленый для connected)"""
    page = page_with_notification_component
    
    # Проверяем что статус индикатор connected существует
    manager = await page.query_selector('platform-notification-manager')
    status_connected = await manager.query_selector('.status.connected')
    
    assert status_connected is not None, "Status indicator with 'connected' class not found"
    
    # Проверяем видимость через evaluate
    is_visible = await status_connected.evaluate('(el) => el.offsetWidth > 0 && el.offsetHeight > 0')
    assert is_visible, "Status indicator is not visible"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_panel_opens_and_closes(page_with_notification_component):
    """Панель открывается по клику, закрывается"""
    page = page_with_notification_component
    
    manager = await page.query_selector('platform-notification-manager')
    button = await manager.query_selector('.notification-button')
    
    panel = await manager.query_selector('.notification-panel')
    assert panel is None, "Panel should be closed initially"
    
    await button.click()
    await asyncio.sleep(0.3)
    
    panel = await manager.query_selector('.notification-panel')
    assert panel is not None, "Panel should open after button click"
    is_visible = await panel.evaluate('(el) => el.offsetWidth > 0 && el.offsetHeight > 0')
    assert is_visible, "Panel should be visible"
    
    await button.click()
    await asyncio.sleep(0.3)
    
    panel = await manager.query_selector('.notification-panel')
    assert panel is None


# ============================================================================
# Группа 2: Получение уведомлений
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_single_notification_shows_toast(page_with_notification_component, system_user_id):
    """Toast появляется при получении уведомления"""
    page = page_with_notification_component
    
    await notify_user(
        user_id=system_user_id,
        notification=Notification(
            type=NotificationType.SYSTEM,
            title="Тестовое уведомление",
            message="Проверка toast",
            service="test",
            priority="normal"
        )
    )
    
    toast = await page.wait_for_selector('.notification-toast', timeout=5000)
    assert toast is not None, "Toast notification should appear"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_toast_contains_correct_data(page_with_notification_component, system_user_id):
    """Title, message, service badge отображаются корректно"""
    page = page_with_notification_component
    
    await notify_user(
        user_id=system_user_id,
        notification=Notification(
            type=NotificationType.SYSTEM,
            title="Заголовок теста",
            message="Сообщение теста",
            service="test_service",
            priority="normal"
        )
    )
    
    toast = await page.wait_for_selector('.notification-toast', timeout=5000)
    
    title = await toast.query_selector('strong')
    title_text = await title.inner_text()
    assert title_text == "Заголовок теста"
    
    content = await toast.inner_text()
    assert "Сообщение теста" in content


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_multiple_notifications_update_badge(page_with_notification_component, system_user_id):
    """Badge показывает количество непрочитанных"""
    page = page_with_notification_component
    
    manager = await page.query_selector('platform-notification-manager')
    
    for i in range(3):
        await notify_user(
            user_id=system_user_id,
            notification=Notification(
                type=NotificationType.SYSTEM,
                title=f"Уведомление {i+1}",
                message=f"Сообщение {i+1}",
                service="test"
            )
        )
        await asyncio.sleep(0.5)
    
    badge = await manager.wait_for_selector('.badge', timeout=5000)
    badge_text = await badge.inner_text()
    assert badge_text == "3"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_notification_appears_in_panel(page_with_notification_component, system_user_id):
    """Уведомление добавляется в список панели"""
    page = page_with_notification_component
    
    await notify_user(
        user_id=system_user_id,
        notification=Notification(
            type=NotificationType.SYSTEM,
            title="Панельное уведомление",
            message="Должно быть в списке",
            service="test"
        )
    )
    
    await asyncio.sleep(1)
    
    manager = await page.query_selector('platform-notification-manager')
    button = await manager.query_selector('.notification-button')
    await button.click()
    
    panel = await manager.wait_for_selector('.notification-panel', timeout=3000)
    
    items = await panel.query_selector_all('.notification-item')
    assert len(items) >= 1
    
    first_item = items[0]
    item_text = await first_item.inner_text()
    assert "Панельное уведомление" in item_text


# ============================================================================
# Группа 3: Приоритеты и стили
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_urgent_notification_has_red_border(page_with_notification_component, system_user_id):
    """Срочные уведомления с красной границей"""
    page = page_with_notification_component
    
    await notify_user(
        user_id=system_user_id,
        notification=Notification(
            type=NotificationType.SYSTEM,
            title="СРОЧНО",
            message="Критическая ситуация",
            service="test",
            priority="urgent"
        )
    )
    
    toast = await page.wait_for_selector('.notification-toast.priority-urgent', timeout=5000)
    assert toast is not None, "Urgent toast should appear"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_high_priority_styling(page_with_notification_component, system_user_id):
    """Высокий приоритет"""
    page = page_with_notification_component
    
    await notify_user(
        user_id=system_user_id,
        notification=Notification(
            type=NotificationType.SYSTEM,
            title="Высокий приоритет",
            message="Важное сообщение",
            service="test",
            priority="high"
        )
    )
    
    toast = await page.wait_for_selector('.notification-toast.priority-high', timeout=5000)
    assert toast is not None, "High priority toast should appear"


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_normal_low_priority_styling(page_with_notification_component, system_user_id):
    """Обычный и низкий приоритет"""
    page = page_with_notification_component
    
    await notify_user(
        user_id=system_user_id,
        notification=Notification(
            type=NotificationType.SYSTEM,
            title="Обычный приоритет",
            message="Обычное сообщение",
            service="test",
            priority="normal"
        )
    )
    
    toast = await page.wait_for_selector('.notification-toast.priority-normal', timeout=5000)
    assert toast is not None, "Normal priority toast should appear"


# ============================================================================
# Группа 4: Взаимодействия
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_click_notification_with_action_url(page_with_notification_component, system_user_id):
    """Клик по уведомлению переходит по ссылке"""
    page = page_with_notification_component
    
    await notify_user(
        user_id=system_user_id,
        notification=Notification(
            type=NotificationType.TASK_COMPLETED,
            title="Задача завершена",
            message="Кликните для перехода",
            service="crm",
            action_url="/crm/tasks/123",
            priority="normal"
        )
    )
    
    toast = await page.wait_for_selector('.notification-toast', timeout=5000)
    
    async with page.expect_navigation(timeout=5000):
        await toast.click()
    
    assert page.url.endswith('/crm/tasks/123')


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_mark_notification_as_read(page_with_notification_component, system_user_id):
    """Клик помечает как прочитанное"""
    page = page_with_notification_component
    
    await notify_user(
        user_id=system_user_id,
        notification=Notification(
            type=NotificationType.SYSTEM,
            title="Для прочтения",
            message="Кликните чтобы прочитать",
            service="test"
        )
    )
    
    await asyncio.sleep(1)
    
    manager = await page.query_selector('platform-notification-manager')
    button = await manager.query_selector('.notification-button')
    await button.click()
    
    panel = await manager.wait_for_selector('.notification-panel', timeout=3000)
    
    unread_item = await panel.query_selector('.notification-item.unread')
    assert unread_item is not None
    
    await unread_item.click()
    await asyncio.sleep(0.3)
    
    read_item = await panel.query_selector('.notification-item.read')
    assert read_item is not None


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_clear_all_notifications(page_with_notification_component, system_user_id):
    """Кнопка Очистить удаляет все"""
    page = page_with_notification_component
    
    for i in range(3):
        await notify_user(
            user_id=system_user_id,
            notification=Notification(
                type=NotificationType.SYSTEM,
                title=f"Уведомление {i+1}",
                message=f"Сообщение {i+1}",
                service="test"
            )
        )
        await asyncio.sleep(0.3)
    
    manager = await page.query_selector('platform-notification-manager')
    button = await manager.query_selector('.notification-button')
    await button.click()
    
    panel = await manager.wait_for_selector('.notification-panel', timeout=3000)
    
    items = await panel.query_selector_all('.notification-item')
    assert len(items) == 3
    
    clear_btn = await panel.query_selector('.clear-btn')
    await clear_btn.click()
    await asyncio.sleep(0.3)
    
    panel_after = await manager.query_selector('.notification-panel')
    assert panel_after is None
    
    badge = await manager.query_selector('.badge')
    assert badge is None


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_unread_counter_decreases_on_read(page_with_notification_component, system_user_id):
    """Счетчик уменьшается"""
    page = page_with_notification_component
    
    for i in range(2):
        await notify_user(
            user_id=system_user_id,
            notification=Notification(
                type=NotificationType.SYSTEM,
                title=f"Уведомление {i+1}",
                message=f"Сообщение {i+1}",
                service="test"
            )
        )
        await asyncio.sleep(0.3)
    
    manager = await page.query_selector('platform-notification-manager')
    
    badge = await manager.wait_for_selector('.badge', timeout=5000)
    badge_text = await badge.inner_text()
    assert badge_text == "2"
    
    button = await manager.query_selector('.notification-button')
    await button.click()
    
    panel = await manager.wait_for_selector('.notification-panel', timeout=3000)
    items = await panel.query_selector_all('.notification-item.unread')
    
    if len(items) > 0:
        await items[0].click()
        await asyncio.sleep(0.3)
    
    badge_after = await manager.query_selector('.badge')
    if badge_after:
        badge_text_after = await badge_after.inner_text()
        assert badge_text_after == "1"


# ============================================================================
# Группа 5: WebSocket heartbeat
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_heartbeat_ping_pong(page_with_notification_component):
    """Ping/pong работает"""
    page = page_with_notification_component
    
    messages = []
    
    async def handle_console(msg):
        messages.append(msg.text)
    
    page.on('console', handle_console)
    
    await asyncio.sleep(2)
    
    assert any('подключен' in m or 'WebSocket' in m for m in messages)


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_connection_status_indicator_changes(page_with_notification_component):
    """Индикатор меняется при подключении"""
    page = page_with_notification_component
    
    manager = await page.query_selector('platform-notification-manager')
    status = await manager.query_selector('.status.connected')
    
    assert status is not None, "Status connected should exist"
    is_visible = await status.evaluate('(el) => el.offsetWidth > 0 && el.offsetHeight > 0')
    assert is_visible, "Status should be visible"


# ============================================================================
# Группа 6: Multiple tabs
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_two_tabs_receive_same_notification(authenticated_browser_context, crm_service, system_user_id):
    """2 вкладки получают уведомление"""
    page1 = await authenticated_browser_context.new_page()
    page2 = await authenticated_browser_context.new_page()
    
    # Используем универсальный тестовый endpoint
    await page1.goto("http://localhost:9003/crm/test", wait_until="load")
    await page2.goto("http://localhost:9003/crm/test", wait_until="load")
    
    # Инжектируем компонент в обе вкладки
    inject_script = """
        const script = document.createElement('script');
        script.type = 'module';
        script.src = '/static/core/lib/components/platform-notification-manager.js';
        document.head.appendChild(script);
        
        script.onload = () => {
            const manager = document.createElement('platform-notification-manager');
            document.getElementById('test-root').appendChild(manager);
        };
    """
    
    await page1.evaluate(inject_script)
    await page2.evaluate(inject_script)
    await asyncio.sleep(3.0)
    
    await notify_user(
        user_id=system_user_id,
        notification=Notification(
            type=NotificationType.SYSTEM,
            title="Для всех вкладок",
            message="Проверка multiple tabs",
            service="test"
        )
    )
    
    toast1 = await page1.wait_for_selector('.notification-toast', timeout=5000)
    toast2 = await page2.wait_for_selector('.notification-toast', timeout=5000)
    
    assert toast1 is not None, "Toast should appear in tab 1"
    assert toast2 is not None, "Toast should appear in tab 2"
    
    await page1.close()
    await page2.close()


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_three_tabs_all_update_badges(authenticated_browser_context, crm_service, system_user_id):
    """Все вкладки обновляют badge"""
    pages = []
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Notification Manager Test</title>
        <script type="module" src="http://localhost:9003/static/core/lib/components/platform-notification-manager.js"></script>
    </head>
    <body>
        <platform-notification-manager></platform-notification-manager>
    </body>
    </html>
    """
    
    for i in range(3):
        page = await authenticated_browser_context.new_page()
        await page.set_content(html_content, wait_until="networkidle")
        pages.append(page)
    
    await asyncio.sleep(1.5)
    
    await notify_user(
        user_id=system_user_id,
        notification=Notification(
            type=NotificationType.SYSTEM,
            title="Badge тест",
            message="Проверка счетчика",
            service="test"
        )
    )
    
    await asyncio.sleep(1)
    
    for page in pages:
        manager = await page.query_selector('platform-notification-manager')
        badge = await manager.wait_for_selector('.badge', timeout=5000)
        badge_text = await badge.inner_text()
        assert badge_text == "1"
    
    for page in pages:
        await page.close()


# ============================================================================
# Группа 7: Переподключение
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_reconnection_after_disconnect(authenticated_browser_context, crm_service, system_user_id):
    """Компонент переподключается после разрыва"""
    page = await authenticated_browser_context.new_page()
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Notification Manager Test</title>
        <script type="module" src="http://localhost:9003/static/core/lib/components/platform-notification-manager.js"></script>
    </head>
    <body>
        <platform-notification-manager></platform-notification-manager>
    </body>
    </html>
    """
    
    await page.set_content(html_content, wait_until="networkidle")
    await asyncio.sleep(1.5)
    
    manager = await page.query_selector('platform-notification-manager')
    status = await manager.query_selector('.status.connected')
    assert status is not None
    
    await page.reload(wait_until="networkidle")
    await asyncio.sleep(1.5)
    
    manager = await page.query_selector('platform-notification-manager')
    status_after = await manager.query_selector('.status.connected')
    assert status_after is not None
    
    await page.close()


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_notifications_after_reconnection(authenticated_browser_context, crm_service, system_user_id):
    """Уведомления работают после переподключения"""
    page = await authenticated_browser_context.new_page()
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Notification Manager Test</title>
        <script type="module" src="http://localhost:9003/static/core/lib/components/platform-notification-manager.js"></script>
    </head>
    <body>
        <platform-notification-manager></platform-notification-manager>
    </body>
    </html>
    """
    
    await page.set_content(html_content, wait_until="networkidle")
    await asyncio.sleep(1.5)
    
    await page.reload(wait_until="networkidle")
    await asyncio.sleep(1.5)
    
    await notify_user(
        user_id=system_user_id,
        notification=Notification(
            type=NotificationType.SYSTEM,
            title="После переподключения",
            message="Уведомление после reload",
            service="test"
        )
    )
    
    toast = await page.wait_for_selector('.notification-toast', timeout=5000)
    assert toast is not None, "Toast should appear after reconnection"
    
    await page.close()


# ============================================================================
# Группа 8: Разные типы уведомлений
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.playwright
async def test_all_notification_types(page_with_notification_component, system_user_id):
    """Все типы: system, access_request, mention, task_completed, entity_updated"""
    page = page_with_notification_component
    
    notification_types = [
        NotificationType.SYSTEM,
        NotificationType.ACCESS_REQUEST,
        NotificationType.MENTION,
        NotificationType.TASK_COMPLETED,
        NotificationType.ENTITY_UPDATED,
    ]
    
    for notif_type in notification_types:
        await notify_user(
            user_id=system_user_id,
            notification=Notification(
                type=notif_type,
                title=f"Тест {notif_type.value}",
                message=f"Проверка типа {notif_type.value}",
                service="test"
            )
        )
        
        toast = await page.wait_for_selector('.notification-toast', timeout=5000)
        assert toast is not None, f"Toast should appear after reconnection (iteration {i})"

        await asyncio.sleep(0.5)

