"""
TaskIQ задачи для инициализации компаний и system.
"""

from typing import Dict, Any
from pathlib import Path

from apps.flows.src.container import get_container
from apps.flows.src.services.flows_loader import FlowsLoader
from apps.flows.src.services.mcp_sync import (
    ensure_default_mcp_servers_for_company,
    sync_auto_mcp_servers_for_company,
)
from core.context import Context, set_context, clear_context
from core.logging import get_logger
from core.models.identity_models import User, Company
from core.models.i18n_models import Language
from apps.flows_worker.broker import broker

logger = get_logger(__name__)


@broker.task(
    task_name="init_company_resources", 
    retry_on_error=True, 
    max_retries=3,
    queue_name="flows_worker"
)
async def init_company_resources(
    company_id: str,
    company_name: str = "",
    subdomain: str = ""
) -> Dict[str, Any]:
    """
    Универсальная задача инициализации ресурсов для компании.
    
    Если company_id == "system":
        Загружает ВСЕ агенты и тулы из registry в system namespace
        (запускается при старте сервиса)
        
    Иначе:
        Загружает ТОЛЬКО PUBLIC агенты и тулы из кода в company namespace
        (запускается при создании компании)
    
    Args:
        company_id: "system" или ID компании
        company_name: Название компании (для логов)
        subdomain: Subdomain компании (slug)
        
    Returns:
        {"flows": count, "tools": count, "nodes": count, "status": "completed"}
    """
    is_system = (company_id == "system")
    action = "Загрузка" if is_system else "Копирование"
    
    logger.info(
        f"{action} ресурсов для компании: {company_id} ({company_name or 'system'})"
    )
    
    # Установить контекст компании
    company_context = Context(
        user=User(user_id="system", name="System", groups=["admin"]),
        host="system",
        session_id=f"init_company_{company_id}",
        channel="system",
        language=Language.RU,
        active_company=Company(
            company_id=company_id,
            name=company_name or company_id,
            subdomain=subdomain or company_id  # Используем subdomain или fallback на company_id
        ),
        user_companies=[],
        trace_id=f"system:init_company:{company_id}",
    )
    set_context(company_context)
    
    try:
        container = get_container()
        
        # Путь к единому registry
        registry_path = Path(__file__).parent.parent.parent / "registry.yaml"
        bundles_dir = Path(__file__).parent.parent.parent / "bundles"
        
        # Загружаем tools (для ВСЕХ компаний, включая system)
        from apps.flows.src.services.flows_loader import load_tools_to_db
        
        loaded_tools = await load_tools_to_db(container.tool_repository)
        logger.info(f"Загружено {len(loaded_tools)} tools для {company_id}")

        await ensure_default_mcp_servers_for_company(container=container)
        synced = await sync_auto_mcp_servers_for_company(container=container)
        logger.info(
            "MCP синхронизация для %s: servers=%s tools=%s",
            company_id,
            synced["servers"],
            synced["tools"],
        )
        
        loader = FlowsLoader(
            bundles_dir=bundles_dir,
            flow_repository=container.flow_repository,
            node_repository=container.node_repository,
            tool_repository=container.tool_repository,
            registry_path=registry_path,
        )
        
        # Универсальный метод - работает и для system и для company
        # Для system фильтр public отключен, для company - включен
        stats = await loader.load_all_for_company(
            company_id=company_id,
            filter_public=(company_id != "system")
        )

        from apps.flows.src.services.operator_demo_queue import ensure_example_hitl_queue

        await ensure_example_hitl_queue(container.operator_repository, company_id)
        
        # Обновляем статистику tools
        stats["tools"] = len(loaded_tools)
        
        logger.info(
            f"{action} завершено для {company_id}: "
            f"flows={stats['flows']}, tools={stats['tools']}, nodes={stats['nodes']}"
        )
        
        return {
            **stats,
            "status": "completed",
            "company_id": company_id,
        }
        
    except Exception as e:
        logger.error(
            f"Ошибка {action.lower()} для {company_id}: {e}", 
            exc_info=True
        )
        raise
    finally:
        clear_context()

