"""
Сценарий: Создание и настройка MCP сервера.

Генерирует пользовательскую документацию в docs/user_docs/user_scenarios/mcp_setup/
"""

import pytest
from playwright.async_api import Page


@pytest.mark.asyncio(loop_scope="session")
class TestMCPSetupScenario:
    """Сценарий создания MCP сервера с генерацией документации"""

    async def test_create_mcp_server(self, page: Page, e2e_base_url: str, doc_generator):
        """Создание и настройка MCP сервера"""
        doc = doc_generator("mcp_setup", "Создание и настройка MCP сервера")
        
        await page.goto(f"{e2e_base_url}/frontend/mcp")
        await page.wait_for_load_state("networkidle")
        
        await page.wait_for_selector(".mcp-server-card-create", timeout=15000)
        await page.wait_for_timeout(500)
        
        await doc.step(
            page,
            "Открытие раздела MCP",
            "Откройте раздел **MCP** в боковом меню. "
            "MCP (Model Context Protocol) позволяет подключать внешние инструменты к вашим ботам."
        )
        
        await doc.click(
            page,
            ".mcp-server-card-create",
            "Добавление сервера",
            "Нажмите на карточку **Добавить MCP сервер** для создания нового подключения."
        )
        
        await page.wait_for_function(
            "document.getElementById('mcp-server-modal')?.style.display === 'flex'",
            timeout=10000
        )
        await page.wait_for_timeout(500)
        
        await doc.step(
            page,
            "Форма настройки",
            "Откроется форма для настройки MCP сервера. Заполните все необходимые поля."
        )
        
        await doc.fill(
            page,
            "#server-id",
            "context7",
            "Ввод ID сервера",
            "Введите **ID сервера** - уникальный идентификатор (латиница, без пробелов). "
            "Например: `context7`, `weather_api`, `my_tools`."
        )
        
        await doc.fill(
            page,
            "#server-name",
            "Context7 Documentation",
            "Ввод названия",
            "Введите **название** сервера - понятное описание для отображения в интерфейсе."
        )
        
        await doc.fill(
            page,
            "#server-description",
            "Поиск документации по библиотекам",
            "Ввод описания",
            "Добавьте **описание** - для чего используется этот MCP сервер."
        )
        
        await doc.fill(
            page,
            "#server-url",
            "https://mcp.context7.com/mcp",
            "Ввод URL",
            "Введите **URL** MCP сервера - адрес для подключения. "
            "Уточните URL в документации сервера."
        )
        
        await doc.step(
            page,
            "Выбор типа транспорта",
            "Выберите **тип транспорта**: HTTP для стандартных запросов "
            "или SSE для серверов с потоковой передачей.",
            "#server-transport-type"
        )
        
        await doc.fill(
            page,
            "#server-headers",
            '{"Authorization": "@var:context7_api_key"}',
            "Настройка заголовков",
            "Настройте **HTTP заголовки** для авторизации. Используйте `@var:key` "
            "для ссылок на переменные (рекомендуется для API ключей)."
        )
        
        await doc.step(
            page,
            "Дополнительные опции",
            "Настройте дополнительные опции:\n"
            "- **Использовать прокси** - для работы через корпоративный прокси\n"
            "- **Активен** - включить/выключить сервер\n"
            "- **Автосинхронизация** - автоматически обновлять список инструментов",
            "#server-is-active"
        )
        
        await doc.click(
            page,
            "button[onclick='saveServer()']",
            "Сохранение сервера",
            "Нажмите кнопку **сохранения** (иконка дискеты) для создания сервера."
        )
        
        await page.wait_for_timeout(1000)
        
        await doc.step(
            page,
            "Синхронизация инструментов",
            "MCP сервер создан! Теперь нажмите кнопку **синхронизации** (иконка обновления) "
            "на карточке сервера, чтобы загрузить список доступных инструментов."
        )
        
        await doc.step(
            page,
            "Использование в ботах",
            "После синхронизации инструменты MCP сервера появятся в настройках ботов "
            "на вкладке **MCP**. Выберите нужные инструменты для каждого бота."
        )
        
        doc.save()
