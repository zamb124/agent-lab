"""
Сценарий: Настройка бота.

Генерирует пользовательскую документацию в docs/user_docs/user_scenarios/bot_settings/
"""

import pytest
from playwright.async_api import Page


@pytest.mark.asyncio(loop_scope="session")
class TestBotSettingsScenario:
    """Сценарий настройки бота с генерацией документации"""

    async def test_configure_bot(self, page: Page, e2e_base_url: str, doc_generator):
        """Настройка существующего бота"""
        doc = doc_generator("bot_settings", "Настройка бота")
        
        await page.goto(f"{e2e_base_url}/frontend/bots")
        await page.wait_for_load_state("networkidle")
        
        # Ждем загрузки HTMX контента
        await page.wait_for_selector(".bot-card", timeout=15000)
        await page.wait_for_timeout(500)
        
        await doc.step(
            page,
            "Откройте раздел **Боты** в боковом меню. "
            "Здесь отображается список всех ваших ботов."
        )
        
        bot_cards = page.locator(".bot-card:not(.bot-card-create)")
        cards_count = await bot_cards.count()
        
        if cards_count == 0:
            pytest.skip("Нет установленных ботов для настройки")
        
        await doc.click(
            page,
            ".bot-card:not(.bot-card-create)",
            "Нажмите на карточку бота, чтобы открыть его настройки."
        )
        
        # Ждем загрузки модалки с деталями бота
        await page.wait_for_selector("#bot-expanded-modal .bot-details-header", timeout=15000)
        await page.wait_for_timeout(500)
        
        await doc.step(
            page,
            "Откроется панель настроек бота с несколькими вкладками: "
            "Основные, Способности, MCP, База знаний, Каналы, Дополнительно."
        )
        
        # Вкладка "Основные"
        await doc.click(
            page,
            ".settings-tab[data-tab='main']",
            "Перейдите на вкладку **Основные** для редактирования базовых настроек."
        )
        
        await page.wait_for_timeout(300)
        
        await doc.step(
            page,
            "На вкладке **Основные** можно изменить описание бота и его промпт (инструкции для ИИ)."
        )
        
        # Редактируем описание
        description_input = page.locator("#bot-description-main")
        if await description_input.count() > 0:
            await doc.fill(
                page,
                "#bot-description-main",
                "Бот для автоматизации поддержки клиентов",
                "Введите **описание бота** - это поможет понять его назначение."
            )
        
        # Вкладка "Способности"
        await doc.click(
            page,
            ".settings-tab[data-tab='abilities']",
            "Перейдите на вкладку **Способности** для управления инструментами бота."
        )
        
        await page.wait_for_timeout(500)
        
        await doc.step(
            page,
            "На вкладке **Способности** отображаются доступные инструменты. "
            "Выбранные инструменты бот сможет использовать при общении с пользователями."
        )
        
        # Вкладка "Каналы"
        await doc.click(
            page,
            ".settings-tab[data-tab='platforms']",
            "Перейдите на вкладку **Каналы** для настройки платформ общения."
        )
        
        await page.wait_for_timeout(300)
        
        await doc.step(
            page,
            "На вкладке **Каналы** можно подключить бота к Telegram, WhatsApp, Web или API. "
            "Каждый канал настраивается отдельно."
        )
        
        # Вкладка "LLM модель"
        await doc.click(
            page,
            ".settings-tab[data-tab='main']",
            "Вернитесь на вкладку **Основные** для настройки модели ИИ."
        )
        
        await page.wait_for_timeout(300)
        
        # Выбор модели
        model_select = page.locator("#bot-llm-model")
        if await model_select.count() > 0:
            await doc.step(
                page,
                "В поле **LLM модель** можно выбрать модель искусственного интеллекта: "
                "Claude, GPT-4, Gemini и другие.",
                "#bot-llm-model"
            )
        
        # Сохранение
        save_btn = page.locator("button[onclick*='saveBotSettings']").first
        if await save_btn.count() > 0:
            await doc.click(
                page,
                "button[onclick*='saveBotSettings']",
                "Нажмите кнопку **сохранения** (иконка дискеты) для применения изменений."
            )
            
            await page.wait_for_timeout(1000)
        
        await doc.step(
            page,
            "Настройки сохранены! Бот готов к работе с новыми параметрами."
        )
        
        doc.save()

