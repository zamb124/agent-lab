"""
Сценарий: Создание и настройка переменных.

Генерирует пользовательскую документацию в docs/user_docs/user_scenarios/variables_setup/
"""

import pytest
from playwright.async_api import Page


@pytest.mark.asyncio(loop_scope="session")
class TestVariablesSetupScenario:
    """Сценарий создания переменной с генерацией документации"""

    async def test_create_variable(self, page: Page, e2e_base_url: str, doc_generator):
        """Создание новой переменной"""
        doc = doc_generator("variables_setup", "Создание и настройка переменных")
        
        await page.goto(f"{e2e_base_url}/frontend/variables")
        await page.wait_for_load_state("networkidle")
        
        await page.wait_for_selector(".variable-card-create", timeout=15000)
        await page.wait_for_timeout(500)
        
        await doc.step(
            page,
            "Открытие раздела Переменные",
            "Откройте раздел **Переменные** в боковом меню. "
            "Здесь отображается список всех переменных компании."
        )
        
        await doc.click(
            page,
            ".variable-card-create",
            "Создание переменной",
            "Нажмите на карточку **Создать переменную** для добавления новой переменной."
        )
        
        await page.wait_for_function(
            "document.getElementById('variable-modal')?.style.display === 'flex'",
            timeout=10000
        )
        await page.wait_for_timeout(500)
        
        await doc.step(
            page,
            "Форма создания",
            "Откроется модальное окно для ввода данных переменной."
        )
        
        await doc.fill(
            page,
            "#variable-key",
            "telegram_bot_token",
            "Ввод ключа",
            "Введите **ключ переменной** - это уникальный идентификатор. "
            "Используйте snake_case без пробелов (например, `telegram_bot_token`)."
        )
        
        await doc.fill(
            page,
            "#variable-description",
            "Токен Telegram бота для уведомлений",
            "Добавление описания",
            "Добавьте **описание** переменной, чтобы потом было понятно её назначение."
        )
        
        await doc.fill(
            page,
            "#variable-value",
            "123456789:ABCdefGHIjklMNOpqrsTUVwxyz",
            "Ввод значения",
            "Введите **значение** переменной. Для API ключей и токенов это обычно длинная строка."
        )
        
        await doc.click(
            page,
            "#variable-secret",
            "Установка флага секрета",
            "Отметьте чекбокс **Секрет**, если значение должно быть скрыто (для паролей и токенов)."
        )
        
        await doc.click(
            page,
            "button[onclick='saveVariable()']",
            "Сохранение переменной",
            "Нажмите кнопку **сохранения** (иконка дискеты) для создания переменной."
        )
        
        await page.wait_for_timeout(1000)
        await page.wait_for_selector("#variables-container", timeout=5000)
        
        await doc.step(
            page,
            "Переменная создана",
            "Переменная создана! Теперь её можно использовать в конфигурации ботов "
            "с помощью синтаксиса `@var:telegram_bot_token`."
        )
        
        doc.save()
