"""
Синхронизация MCP тулов с БД.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from apps.agents.models import ToolReference
from apps.agents.models.core_models import CodeMode
from apps.agents.container import get_agents_container
from apps.agents.services.mcp_client import get_mcp_client
from core.context import get_context

logger = logging.getLogger(__name__)


async def sync_mcp_server_tools(server_id: str, company_id: Optional[str] = None) -> List[ToolReference]:
    """
    Синхронизирует тулы MCP сервера для компании.
    
    1. Подключается к MCP серверу компании
    2. Получает список доступных тулов
    3. Создает ToolReference для каждого
    4. Сохраняет в БД
    5. Обновляет кэш в конфигурации сервера
    
    Args:
        server_id: ID MCP сервера
        company_id: ID компании (опционально, из контекста)
        
    Returns:
        Список созданных ToolReference
    """
    # Определяем company_id (для логирования)
    if company_id is None:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Не удалось определить company_id для синхронизации")
        company_id = context.active_company.company_id
    
    mcp_repo = get_agents_container().mcp_server_repository
    
    server_config = await mcp_repo.get(server_id)
    if not server_config:
        raise ValueError(f"MCP сервер {server_id} не найден для компании {company_id}")
    
    if not server_config.is_active:
        raise ValueError(f"MCP сервер {server_id} неактивен")
    
    logger.info(f"🔄 Синхронизация MCP сервера {server_id} для компании {company_id}")
    
    # Получаем клиент
    mcp_client = await get_mcp_client(server_id, company_id)
    
    # Получаем список тулов от MCP сервера
    tools_data = await mcp_client.list_tools()
    
    # Создаем ToolReference для каждого тула
    tool_references = []
    tool_repo = get_agents_container().tool_repository
    
    for mcp_tool in tools_data:
        tool_name = mcp_tool.get("name")
        if not tool_name:
            logger.warning(f"Пропускаем тул без имени: {mcp_tool}")
            continue
        
        tool_id = f"mcp:{server_id}:{tool_name}"
        
        tool_ref = ToolReference(
            tool_id=tool_id,
            title=mcp_tool.get("title") or tool_name,
            group=f"MCP: {server_config.name}",
            description=mcp_tool.get("description", ""),
            params={
                "server_id": server_id,
                "company_id": company_id,
                "tool_name": tool_name,
                "input_schema": mcp_tool.get("inputSchema", {})
            },
            code_mode=CodeMode.MCP_TOOL,
            function_path=None,
            inline_code=None,
            cost=mcp_tool.get("cost", 0.0),
            billing_name=f"mcp_{server_id}_{tool_name}",
            is_public=False,
            source="mcp_sync"
        )
        
        await tool_repo.set(tool_ref)
        tool_references.append(tool_ref)
        
        logger.info(f"✅ Синхронизирован MCP тул: {tool_id}")
    
    # Обновляем кэш в конфигурации сервера
    server_config.cached_tools = [t.tool_id for t in tool_references]
    server_config.last_sync_at = datetime.now(timezone.utc)
    await mcp_repo.set(server_config)
    
    logger.info(
        f"✅ Синхронизировано {len(tool_references)} тулов "
        f"для MCP сервера {server_id} (компания {company_id})"
    )
    
    return tool_references


async def sync_all_mcp_servers_for_company(company_id: Optional[str] = None):
    """
    Синхронизирует все активные MCP серверы компании.
    
    Args:
        company_id: ID компании (опционально, из контекста)
    """
    if company_id is None:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Не удалось определить company_id")
        company_id = context.active_company.company_id
    
    mcp_repo = get_agents_container().mcp_server_repository
    
    active_servers = await mcp_repo.list_active()
    
    if not active_servers:
        logger.info(f"Нет активных MCP серверов для компании {company_id}")
        return
    
    logger.info(f"🔌 Синхронизация {len(active_servers)} MCP серверов для компании {company_id}")
    
    total_tools = 0
    for server_config in active_servers:
        if server_config.auto_sync_tools:
            try:
                tools = await sync_mcp_server_tools(server_config.server_id, company_id)
                total_tools += len(tools)
            except Exception as e:
                logger.error(
                    f"❌ Ошибка синхронизации MCP сервера {server_config.server_id}: {e}",
                    exc_info=True
                )
    
    logger.info(f"✅ Всего синхронизировано {total_tools} MCP тулов")


async def sync_all_companies_mcp_servers():
    """
    Синхронизирует MCP серверы для всех компаний.
    Используется при старте приложения.
    """
    container = get_agents_container()
    mcp_repo = container.mcp_server_repository
    
    # Получаем все MCP серверы текущей компании
    all_servers = await mcp_repo.list_all(limit=10000)
    
    if not all_servers:
        logger.info("Нет MCP серверов для синхронизации")
        return
    
    context = get_context()
    company_id = context.active_company.company_id if context and context.active_company else "unknown"
    
    logger.info(f"🔌 Синхронизация {len(all_servers)} MCP серверов для компании {company_id}")
    
    try:
        await sync_all_mcp_servers_for_company(company_id)
    except Exception as e:
        logger.error(f"❌ Ошибка синхронизации MCP для компании {company_id}: {e}", exc_info=True)

