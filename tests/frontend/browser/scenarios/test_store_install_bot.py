"""
Сценарий: Установка бота из магазина и общение с ним.

Полный цикл:
1. Зайти в магазин (store)
2. Открыть детали flow
3. Нажать "Установить"
4. После установки - перейти на страницу ботов
5. Найти установленного бота
6. Открыть его детали
7. Нажать "Запустить" (открыть чат)
8. Написать сообщение боту
9. Получить ответ

Страницы используют HTMX - контент загружается динамически.
"""

import pytest
from playwright.async_api import Page, expect


@pytest.mark.asyncio(loop_scope="session")
class TestDatabaseDiagnostics:
    """Диагностические тесты для проверки работы БД между процессами"""

    async def test_server_can_read_e2e_user(self, page: Page, server_url: str, e2e_test_data):
        """Проверяем что сервер может прочитать E2E пользователя из БД"""
        user_id = e2e_test_data["user_id"]
        
        # Делаем запрос к debug endpoint
        response = await page.request.get(f"{server_url}/debug/check-user/{user_id}")
        data = await response.json()
        
        print(f"\n=== Database Diagnostics ===")
        print(f"User ID: {user_id}")
        print(f"Server response: {data}")
        print(f"User exists in server DB: {data.get('exists')}")
        print(f"Server shared_db_url: {data.get('shared_db_url')}")
        print(f"===========================\n")
        
        assert data.get("exists"), f"Сервер не может найти пользователя {user_id}! Response: {data}"

    async def test_pytest_can_read_e2e_user(self, migrated_db, e2e_test_data):
        """Проверяем что pytest может прочитать E2E пользователя из БД"""
        from apps.agents.container import get_agents_container
        
        user_id = e2e_test_data["user_id"]
        container = get_agents_container()
        user = await container.user_repository.get(user_id)
        
        print(f"\n=== Pytest Database Check ===")
        print(f"User ID: {user_id}")
        print(f"User found: {user is not None}")
        if user:
            print(f"User name: {user.name}")
            print(f"User companies: {user.companies}")
        print(f"=============================\n")
        
        assert user is not None, f"pytest не может найти пользователя {user_id}"


@pytest.mark.asyncio(loop_scope="session")
class TestStoreInstallBotScenario:
    """Полный сценарий установки и общения с ботом"""

    async def _wait_for_htmx_content(self, page: Page, selector: str, timeout: int = 15000):
        """Ждет появления контента загруженного через HTMX"""
        try:
            await page.wait_for_selector(selector, timeout=timeout)
            return True
        except:
            return False

    async def _wait_and_screenshot(self, page: Page, screenshots, name: str, wait_selector: str = None):
        """Ждет загрузки и делает скриншот"""
        if wait_selector:
            await self._wait_for_htmx_content(page, wait_selector)
        await page.wait_for_load_state("networkidle")
        await screenshots.capture(name, page)

    async def test_store_page_loads(self, page: Page, e2e_base_url: str, scenario_screenshots):
        """Шаг 1: Проверяем загрузку страницы магазина"""
        response = await page.goto(f"{e2e_base_url}/frontend/store")
        await page.wait_for_load_state("domcontentloaded")
        await scenario_screenshots.capture("store_initial", page)
        
        # Проверяем что не редирект
        current_url = page.url
        assert "/auth" not in current_url, f"Редирект на авторизацию: {current_url}"
        assert "/select-company" not in current_url, f"Редирект на выбор компании: {current_url}"
        
        # Ждем загрузки HTMX контента
        await self._wait_for_htmx_content(
            page, 
            "#store-list-view .store-card, #store-list-view .store-grid",
            timeout=15000
        )
        await scenario_screenshots.capture("store_loaded", page)
        
        # Проверяем что контент загрузился
        store_container = page.locator("#store-list-view")
        container_html = await store_container.inner_html()
        assert len(container_html) > 50, f"HTMX контент не загрузился"

    async def test_open_flow_details(self, page: Page, e2e_base_url: str, scenario_screenshots):
        """Шаг 2: Открываем детали первого flow в магазине"""
        await page.goto(f"{e2e_base_url}/frontend/store")
        await page.wait_for_load_state("domcontentloaded")
        
        # Ждем загрузки карточек
        await self._wait_for_htmx_content(page, ".store-card", timeout=15000)
        await scenario_screenshots.capture("store_before_click", page)
        
        # Находим первую карточку flow
        store_cards = page.locator(".store-card")
        cards_count = await store_cards.count()
        
        if cards_count == 0:
            pytest.skip("Нет доступных flows в магазине")
        
        # Кликаем на первую карточку
        first_card = store_cards.first
        flow_name = await first_card.locator(".store-card-title").text_content()
        await first_card.click()
        
        # Ждем появления модалки с деталями
        await self._wait_for_htmx_content(page, "#flow-details-modal .flow-modal-header", timeout=10000)
        await scenario_screenshots.capture("flow_details_modal", page)
        
        # Проверяем что модалка открылась
        modal = page.locator("#flow-details-modal")
        await expect(modal).to_be_visible(timeout=5000)
        
        # Проверяем наличие кнопки установки или удаления
        install_btn = page.locator("button:has-text('Установить')")
        uninstall_btn = page.locator("button:has-text('Удалить')")
        
        is_installed = await uninstall_btn.count() > 0
        assert await install_btn.count() > 0 or is_installed, "Нет кнопки установки/удаления"

    async def test_install_flow_and_navigate_to_bots(self, page: Page, e2e_base_url: str, scenario_screenshots):
        """Шаг 3-4: Устанавливаем flow (если не установлен) и переходим к ботам"""
        await page.goto(f"{e2e_base_url}/frontend/store")
        await page.wait_for_load_state("domcontentloaded")
        await self._wait_for_htmx_content(page, ".store-card", timeout=15000)
        
        # Ищем НЕустановленный flow (без badge "Установлено")
        not_installed_cards = page.locator(".store-card:not(.installed)")
        installed_cards = page.locator(".store-card.installed")
        
        not_installed_count = await not_installed_cards.count()
        installed_count = await installed_cards.count()
        
        await scenario_screenshots.capture("store_flows_list", page)
        
        if not_installed_count > 0:
            # Есть неустановленный flow - устанавливаем
            await not_installed_cards.first.click()
            await self._wait_for_htmx_content(page, "#flow-details-modal .flow-modal-header", timeout=10000)
            await scenario_screenshots.capture("flow_to_install", page)
            
            # Проверяем наличие формы переменных
            variables_form = page.locator("#variables-form")
            has_variables = await variables_form.count() > 0
            
            if has_variables:
                # Заполняем обязательные переменные
                required_inputs = page.locator("#variables-form input[required]")
                for i in range(await required_inputs.count()):
                    input_el = required_inputs.nth(i)
                    current_value = await input_el.input_value()
                    if not current_value:
                        await input_el.fill("test_value_for_e2e")
                await scenario_screenshots.capture("variables_filled", page)
            
            # Устанавливаем обработчик диалога подтверждения
            page.on("dialog", lambda dialog: dialog.accept())
            
            # Нажимаем "Установить"
            install_btn = page.locator("button:has-text('Установить')")
            await install_btn.click()
            
            # Ждем завершения установки и перехода на страницу ботов
            await page.wait_for_timeout(3000)
            await scenario_screenshots.capture("after_install", page)
            
        elif installed_count > 0:
            # Все flows уже установлены - просто переходим к ботам
            await scenario_screenshots.capture("all_flows_installed", page)
        else:
            pytest.skip("Нет доступных flows")
        
        # Переходим на страницу ботов
        await page.goto(f"{e2e_base_url}/frontend/bots")
        await page.wait_for_load_state("domcontentloaded")
        await self._wait_for_htmx_content(page, "#bots-list-view .bot-card", timeout=15000)
        await scenario_screenshots.capture("bots_page", page)
        
        # Проверяем что есть хотя бы один бот
        bot_cards = page.locator(".bot-card:not(.bot-card-create)")
        assert await bot_cards.count() > 0, "Нет установленных ботов"

    async def test_open_bot_details(self, page: Page, e2e_base_url: str, scenario_screenshots):
        """Шаг 5-6: Открываем детали бота"""
        await page.goto(f"{e2e_base_url}/frontend/bots")
        await page.wait_for_load_state("domcontentloaded")
        await self._wait_for_htmx_content(page, "#bots-list-view .bot-card", timeout=15000)
        await scenario_screenshots.capture("bots_list", page)
        
        # Находим первого бота (не карточку "Создать")
        bot_cards = page.locator(".bot-card:not(.bot-card-create)")
        cards_count = await bot_cards.count()
        
        if cards_count == 0:
            pytest.skip("Нет установленных ботов")
        
        # Кликаем на первого бота
        first_bot = bot_cards.first
        bot_name = await first_bot.locator(".bot-name").text_content()
        await first_bot.click()
        
        # Ждем появления модалки с деталями бота
        await self._wait_for_htmx_content(page, "#bot-expanded-modal .bot-details-header", timeout=10000)
        await scenario_screenshots.capture("bot_details_modal", page)
        
        # Проверяем что модалка открылась
        modal = page.locator("#bot-expanded-modal")
        await expect(modal).to_be_visible(timeout=5000)
        
        # Проверяем наличие кнопки "Запустить" (чат)
        launch_btn = page.locator("button:has-text('Запустить'), button:has-text('Launch')")
        assert await launch_btn.count() > 0 or await page.locator(".ti-message-dots").count() > 0, "Нет кнопки запуска чата"

    async def test_open_chat_and_send_message(self, page: Page, e2e_base_url: str, scenario_screenshots):
        """Шаг 7-9: Открываем чат и отправляем сообщение"""
        await page.goto(f"{e2e_base_url}/frontend/bots")
        await page.wait_for_load_state("domcontentloaded")
        await self._wait_for_htmx_content(page, "#bots-list-view .bot-card", timeout=15000)
        
        # Находим первого бота
        bot_cards = page.locator(".bot-card:not(.bot-card-create)")
        if await bot_cards.count() == 0:
            pytest.skip("Нет установленных ботов")
        
        # Открываем детали бота
        await bot_cards.first.click()
        await self._wait_for_htmx_content(page, "#bot-expanded-modal .bot-details-header", timeout=10000)
        await scenario_screenshots.capture("bot_opened", page)
        
        # Нажимаем кнопку "Запустить" (открывает чат)
        launch_btn = page.locator("button:has-text('Запустить')").first
        if await launch_btn.count() > 0:
            await launch_btn.click()
            # Ждем пока чат виджет станет видимым
            await page.wait_for_selector("#chat-widget:not(.hidden)", timeout=5000)
            await page.wait_for_timeout(1000)
            await scenario_screenshots.capture("chat_opened", page)
        
        # Ищем чат виджет
        chat_widget = page.locator("#chat-widget:not(.hidden)")
        chat_input = page.locator("#chat-widget-input")
        
        if await chat_widget.count() > 0 and await chat_input.count() > 0:
            # Ждем пока WebSocket подключится (индикатор connected)
            try:
                await page.wait_for_selector(".connection-indicator.connected", timeout=10000)
                await scenario_screenshots.capture("websocket_connected", page)
            except:
                await scenario_screenshots.capture("websocket_not_connected", page)
            
            # Вводим сообщение
            await chat_input.fill("Привет! Это тестовое сообщение от E2E теста.")
            await scenario_screenshots.capture("message_typed", page)
            
            # Отправляем сообщение
            send_btn = page.locator("#chat-widget-send")
            if await send_btn.count() > 0:
                await send_btn.click()
                
                # Ждем появления сообщения пользователя в чате (приходит через WebSocket)
                try:
                    # Ждем пока появится сообщение пользователя
                    await page.wait_for_selector("#chat-widget-messages .chat-message.user", timeout=15000)
                    await scenario_screenshots.capture("user_message_appeared", page)
                except:
                    await scenario_screenshots.capture("no_user_message", page)
                
                # Ждем ответа бота (воркер должен обработать и вернуть ответ)
                try:
                    # Ждем пока появится сообщение агента
                    await page.wait_for_selector("#chat-widget-messages .chat-message.agent", timeout=30000)
                    await scenario_screenshots.capture("agent_response_appeared", page)
                except:
                    await scenario_screenshots.capture("no_agent_response", page)
                
                await scenario_screenshots.capture("final_chat_state", page)
                
                # Проверяем количество сообщений в чате
                user_messages = page.locator("#chat-widget-messages .chat-message.user")
                agent_messages = page.locator("#chat-widget-messages .chat-message.agent")
                user_count = await user_messages.count()
                agent_count = await agent_messages.count()
                print(f"Сообщений пользователя: {user_count}, ответов агента: {agent_count}")
                
                # Проверяем что есть хотя бы одно сообщение пользователя
                assert user_count > 0, "Сообщение пользователя не появилось в чате"

    async def test_full_navigation_scenario(self, page: Page, e2e_base_url: str, scenario_screenshots):
        """Полный сценарий навигации: Dashboard -> Store -> Bots -> Variables -> History"""
        # Dashboard
        await page.goto(f"{e2e_base_url}/frontend/dashboard")
        await page.wait_for_load_state("networkidle")
        await scenario_screenshots.capture("nav_dashboard", page)
        assert "/auth" not in page.url
        
        # Store
        await page.goto(f"{e2e_base_url}/frontend/store")
        await page.wait_for_load_state("domcontentloaded")
        await self._wait_for_htmx_content(page, "#store-list-view")
        await scenario_screenshots.capture("nav_store", page)
        
        # Bots
        await page.goto(f"{e2e_base_url}/frontend/bots")
        await page.wait_for_load_state("domcontentloaded")
        await self._wait_for_htmx_content(page, "#bots-list-view")
        await scenario_screenshots.capture("nav_bots", page)
        
        # Variables
        await page.goto(f"{e2e_base_url}/frontend/variables")
        await page.wait_for_load_state("networkidle")
        await scenario_screenshots.capture("nav_variables", page)
        
        # History
        await page.goto(f"{e2e_base_url}/frontend/history")
        await page.wait_for_load_state("networkidle")
        await scenario_screenshots.capture("nav_history", page)
        
        # Abilities
        await page.goto(f"{e2e_base_url}/frontend/abilities")
        await page.wait_for_load_state("networkidle")
        await scenario_screenshots.capture("nav_abilities", page)
        
        # MCP
        await page.goto(f"{e2e_base_url}/frontend/mcp")
        await page.wait_for_load_state("networkidle")
        await scenario_screenshots.capture("nav_mcp", page)
