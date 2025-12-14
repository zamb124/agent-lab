"""
Скрипт для настройки MCP сервера Figma Designer.
Выполняет:
1. Создание MCPServerConfig
2. Синхронизацию тулов
3. Настройку переменных компании
"""

import asyncio
import sys
import os

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from apps.agents.models.mcp_models import MCPServerConfig, MCPTransportType
from apps.agents.db.repositories.mcp_repository import MCPServerRepository
from apps.agents.services.mcp_sync import sync_mcp_server_tools
from apps.agents.container import get_agents_container
from core.context import set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User, UserStatus


async def setup_figma_mcp():
    """Настройка MCP сервера для Figma Designer"""

    print("🚀 Настройка MCP сервера Figma Designer...")

    # Инициализируем системный контейнер
    container = get_agents_container()

    # Получаем системную компанию
    storage = container.storage
    company_data = await storage.get("company:system", force_global=True)
    if not company_data:
        print("❌ Системная компания не найдена. Запустите миграцию сначала.")
        return

    company = Company.model_validate_json(company_data)

    # Создаем системного пользователя для скрипта
    system_user = User(
        user_id="system_setup",
        name="System Setup",
        status=UserStatus.ACTIVE,
        groups=["system"],
        companies={company.company_id: ["admin"]},
        active_company_id=company.company_id
    )

    # Устанавливаем контекст
    context = Context(
        user=system_user,
        platform="setup_script",
        active_company=company,
        user_companies=[company]
    )
    set_context(context)

    # Запрашиваем параметры
    print("\n📋 Введите параметры для настройки:")

    # Для SSE транспорта используем базовый URL без /mcp
    # supergateway предоставляет /sse и /message endpoints
    # mcp_url = input("URL MCP сервера (например, http://localhost:3000): ").strip()
    mcp_url = 'http://localhost:3000'
    if not mcp_url:
        print("❌ URL обязателен")
        return

    # Убираем /mcp или /sse из URL, если есть
    mcp_url = mcp_url.rstrip("/")
    if mcp_url.endswith("/mcp") or mcp_url.endswith("/sse"):
        mcp_url = mcp_url.rsplit("/", 1)[0]
        print(f"ℹ️  Используем базовый URL: {mcp_url}")

    # figma_api_token = input("Figma API токен (или нажмите Enter для пропуска): ").strip()
    figma_api_token = 'some'
    # figma_file_key = input("Figma file key проекта (или нажмите Enter для пропуска): ").strip()
    figma_file_key = 'v2RWhDOkvqAhjqKgiVeYTC'
    # figma_page_id = input("Figma page ID (или нажмите Enter для дефолта '1:16'): ").strip() or "1:16"
    figma_page_id = '1:16'

    # Настраиваем переменные компании (нужно сделать до создания сервера)
    print("\n🔧 Настройка переменных компании...")
    variables_service = container.variables_service

    headers = {}
    if figma_api_token:
        await variables_service.set_var(
            "figma_api_token",
            figma_api_token,
            is_secret=True,
            description="Figma API токен для MCP сервера"
        )
        headers["Authorization"] = "@var:figma_api_token"
        print("✅ Переменная figma_api_token установлена")

    # Создаем MCP сервер
    print("\n📦 Создание MCP сервера...")
    mcp_repo = MCPServerRepository(storage)

    server_config = MCPServerConfig(
        server_id="figma_designer",
        company_id=company.company_id,
        name="Figma Designer MCP",
        description="MCP сервер для работы с Figma через cursor-talk-to-figma-mcp (SSE)",
        url=mcp_url,
        transport_type=MCPTransportType.SSE,  # Используем SSE транспорт для supergateway
        headers=headers,
        is_active=True,
        auto_sync_tools=True
    )

    await mcp_repo.set(server_config)
    print(f"✅ MCP сервер создан: {server_config.server_id}")

    # Синхронизируем тулы
    print("\n🔄 Синхронизация MCP тулов...")
    print(f"   Используется SSE транспорт с базовым URL: {mcp_url}")
    print("   Ожидаемые endpoints:")
    print(f"   - GET {mcp_url}/sse (SSE поток)")
    print(f"   - POST {mcp_url}/message (JSON-RPC запросы)")
    try:
        tools = await sync_mcp_server_tools("figma_designer", company.company_id)
        print(f"✅ Синхронизировано {len(tools)} тулов:")
        tool_ids = []
        for tool in tools:
            print(f"   - {tool.tool_id}")
            tool_ids.append(f'        "{tool.tool_id}",')

        print("\n📝 Добавьте эти тулы в apps/agents/agents/figma_designer/agent.py:")
        print("    tools = [")
        print("        ask_user,")
        for tool_id in tool_ids:
            print(tool_id)
        print("        # Сессионные тулы")
        print('        "app.tools.session.session_tools.session_set",')
        print('        "app.tools.session.session_tools.session_get",')
        print("    ]")

    except Exception as e:
        print(f"⚠️ Ошибка синхронизации тулов: {e}")
        print("\n   Проверьте:")
        print(f"   1. Supergateway запущен и доступен на {mcp_url}")
        print("   2. Supergateway настроен с параметрами:")
        print("      --sse http://localhost:3000/sse")
        print("      --port 3000")
        print("      --ssePath /sse")
        print("      --messagePath /message")
        print("   3. MCP сервер (cursor-talk-to-figma-mcp) запущен")
        import traceback
        traceback.print_exc()
        return

    # Настраиваем остальные переменные компании
    if figma_file_key:
        await variables_service.set_var(
            "figma_file_key",
            figma_file_key,
            is_secret=False,
            description="Figma file key проекта"
        )
        print("✅ Переменная figma_file_key установлена")

    if figma_page_id:
        await variables_service.set_var(
            "figma_page_id",
            figma_page_id,
            is_secret=False,
            description="Figma page ID"
        )
        print("✅ Переменная figma_page_id установлена")

    print("\n✅ Настройка завершена!")
    print("\n📝 Следующие шаги:")
    print("1. Раскомментируйте MCP тулы в apps/agents/agents/figma_designer/agent.py")
    print("2. Запустите миграцию для обновления агента в БД")


if __name__ == "__main__":
    asyncio.run(setup_figma_mcp())

