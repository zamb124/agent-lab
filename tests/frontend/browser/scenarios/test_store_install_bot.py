"""
Сценарий: Установка бота из магазина и общение с ним.

Генерирует пользовательскую документацию в docs/user_docs/user_scenarios/store_install_bot/
"""

import pytest
from playwright.async_api import Page


@pytest.mark.asyncio(loop_scope="session")
class TestDatabaseDiagnostics:
    """Диагностические тесты для проверки работы БД между процессами"""

    async def test_server_can_read_e2e_user(self, page: Page, server_url: str, e2e_test_data):
        """Проверяем что сервер может прочитать E2E пользователя из БД"""
        user_id = e2e_test_data["user_id"]
        
        response = await page.request.get(f"{server_url}/debug/check-user/{user_id}")
        data = await response.json()
        
        print("\n=== Database Diagnostics ===")
        print(f"User ID: {user_id}")
        print(f"Server response: {data}")
        print(f"User exists in server DB: {data.get('exists')}")
        print(f"Server shared_db_url: {data.get('shared_db_url')}")
        print("===========================\n")
        
        assert data.get("exists"), f"Сервер не может найти пользователя {user_id}! Response: {data}"

    async def test_pytest_can_read_e2e_user(self, migrated_db, e2e_test_data):
        """Проверяем что pytest может прочитать E2E пользователя из БД"""
        from apps.agents.container import get_agents_container
        
        user_id = e2e_test_data["user_id"]
        container = get_agents_container()
        user = await container.user_repository.get(user_id)
        
        print("\n=== Pytest Database Check ===")
        print(f"User ID: {user_id}")
        print(f"User found: {user is not None}")
        if user:
            print(f"User name: {user.name}")
            print(f"User companies: {user.companies}")
        print("=============================\n")
        
        assert user is not None, f"pytest не может найти пользователя {user_id}"


@pytest.mark.asyncio(loop_scope="session")
class TestStoreInstallBotScenario:
    """Сценарий установки бота из магазина с генерацией документации"""

    async def _wait_for_htmx_content(self, page: Page, selector: str, timeout: int = 15000):
        """Ждет появления контента загруженного через HTMX"""
        try:
            await page.wait_for_selector(selector, timeout=timeout)
            return True
        except:
            return False

    async def test_install_bot_from_store(self, page: Page, e2e_base_url: str, doc_generator):
        """Установка бота из магазина"""
        doc = doc_generator("store_install_bot", "Установка бота из магазина")
        
        # Шаг 1: Открываем магазин
        await page.goto(f"{e2e_base_url}/frontend/store")
        await page.wait_for_load_state("domcontentloaded")
        await self._wait_for_htmx_content(page, ".store-card", timeout=15000)
        await page.wait_for_timeout(500)
        
        await doc.step(
            page,
            "Открытие магазина",
            "Откройте раздел **Магазин** в боковом меню. "
            "Здесь представлены доступные для установки боты."
        )
        
        # Проверяем наличие карточек
        store_cards = page.locator(".store-card")
        cards_count = await store_cards.count()
        
        if cards_count == 0:
            pytest.skip("Нет доступных ботов в магазине")
        
        # Шаг 2: Открываем детали бота
        await doc.click(
            page,
            ".store-card",
            "Выбор бота",
            "Нажмите на карточку бота, чтобы открыть его описание."
        )
        
        await self._wait_for_htmx_content(page, "#flow-details-modal .flow-modal-header", timeout=10000)
        await page.wait_for_timeout(500)
        
        await doc.step(
            page,
            "Просмотр описания",
            "Откроется окно с подробным описанием бота: его возможности, "
            "список способностей и необходимые настройки."
        )
        
        # Проверяем наличие кнопки установки
        install_btn = page.locator("button:has-text('Установить')")
        uninstall_btn = page.locator("button:has-text('Удалить')")
        is_installed = await uninstall_btn.count() > 0
        
        if is_installed:
            # Бот уже установлен - сценарий уже выполнен
            await doc.step(
                page,
                "Бот установлен",
                "Этот бот уже установлен. Вы можете найти его в разделе **Боты**."
            )
            doc.save()
            return
        
        # Шаг 3: Проверяем форму переменных
        variables_form = page.locator("#variables-form")
        has_variables = await variables_form.count() > 0
        
        if has_variables:
            await doc.step(
                page,
                "Настройка переменных",
                "Некоторые боты требуют настройки переменных перед установкой. "
                "Заполните обязательные поля (отмечены звёздочкой)."
            )
            
            # Заполняем обязательные поля
            required_inputs = page.locator("#variables-form input[required]")
            for i in range(await required_inputs.count()):
                input_el = required_inputs.nth(i)
                current_value = await input_el.input_value()
                if not current_value:
                    await input_el.fill("test_value")
        
        # Шаг 4: Устанавливаем бота
        page.on("dialog", lambda dialog: dialog.accept())
        
        # Находим кнопку установки
        install_btn = page.locator("button:has-text('Установить')").first
        await doc.step(page, "Установка", "Нажмите кнопку **Установить** для добавления бота в ваш аккаунт.")
        await install_btn.click()
        
        # Ждем завершения установки
        await page.wait_for_timeout(3000)
        
        await doc.step(
            page,
            "Завершение",
            "После установки бот появится в разделе **Боты**. "
            "Вы можете запустить его и начать общение."
        )
        
        doc.save()

    async def test_open_chat_and_send_message(self, page: Page, e2e_base_url: str, doc_generator):
        """Открытие чата и отправка сообщения боту"""
        doc = doc_generator("chat_with_bot", "Общение с ботом")
        
        # Переходим к ботам
        await page.goto(f"{e2e_base_url}/frontend/bots")
        await page.wait_for_load_state("domcontentloaded")
        await self._wait_for_htmx_content(page, "#bots-list-view .bot-card", timeout=15000)
        await page.wait_for_timeout(500)
        
        await doc.step(
            page,
            "Открытие ботов",
            "Откройте раздел **Боты** в боковом меню. "
            "Здесь отображаются все установленные боты."
        )
        
        bot_cards = page.locator(".bot-card:not(.bot-card-create)")
        if await bot_cards.count() == 0:
            pytest.skip("Нет установленных ботов")
        
        # Открываем детали бота
        await doc.click(
            page,
            ".bot-card:not(.bot-card-create)",
            "Выбор бота",
            "Нажмите на карточку бота для открытия его настроек."
        )
        
        await self._wait_for_htmx_content(page, "#bot-expanded-modal .bot-details-header", timeout=10000)
        await page.wait_for_timeout(500)
        
        await doc.step(
            page,
            "Панель управления",
            "Откроется панель управления ботом с настройками и кнопкой запуска."
        )
        
        # Запускаем чат
        launch_btn = page.locator("button:has-text('Запустить')").first
        if await launch_btn.count() > 0:
            await doc.step(page, "Запуск чата", "Нажмите кнопку **Запустить** для открытия чата с ботом.")
            await launch_btn.click()
            
            await page.wait_for_selector("#chat-widget:not(.hidden)", timeout=5000)
            await page.wait_for_timeout(1000)
        
        # Ждем подключения WebSocket
        try:
            await page.wait_for_selector(".connection-indicator.connected", timeout=10000)
        except:
            pass
        
        await doc.step(
            page,
            "Подключение",
            "Откроется окно чата. Дождитесь подключения (индикатор станет зелёным)."
        )
        
        # Отправляем сообщение
        chat_input = page.locator("#chat-widget-input")
        if await chat_input.count() > 0:
            await doc.fill(
                page,
                "#chat-widget-input",
                "Привет! Расскажи о себе.",
                "Ввод сообщения",
                "Введите сообщение в поле ввода внизу чата."
            )
            
            await doc.click(
                page,
                "#chat-widget-send",
                "Отправка",
                "Нажмите кнопку отправки или клавишу Enter."
            )
            
            # Ждем ответа
            try:
                await page.wait_for_selector("#chat-widget-messages .chat-message.user", timeout=15000)
                await page.wait_for_selector("#chat-widget-messages .chat-message.agent", timeout=30000)
            except:
                pass
            
            await doc.step(
                page,
                "Ответ бота",
                "Бот обработает ваше сообщение и отправит ответ. "
                "Вы можете продолжить диалог, задавая вопросы."
            )
        
        # Проверяем наличие сообщений
        user_messages = page.locator("#chat-widget-messages .chat-message.user")
        user_count = await user_messages.count()
        
        assert user_count > 0, "Сообщение пользователя не появилось в чате"
        
        doc.save()

    async def test_full_navigation_scenario(self, page: Page, e2e_base_url: str, scenario_screenshots):
        """Полный сценарий навигации (без генерации документации)"""
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
