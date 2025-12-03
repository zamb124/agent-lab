"""
TaskIQ задачи для управления компаниями.

Включает асинхронное удаление компании со всеми данными.
"""

import logging
from typing import Any, Dict
from datetime import datetime, timezone

from core.tasks.broker import broker
from apps.agents.container import get_agents_container

logger = logging.getLogger(__name__)


COMPANY_DATA_PREFIXES = [
    "agent:",
    "flow:",
    "tool:",
    "session:",
    "mcp_server:",
    "store:",
    "agent_state:",
    "usage:",
    "file:",
]

COMPANY_VARIABLE_PREFIXES = [
    "var:",
]


@broker.task(retry_on_error=True, max_retries=3)
async def delete_company_task(
    company_id: str,
    initiated_by_user_id: str,
) -> Dict[str, Any]:
    """
    Асинхронное удаление компании со всеми данными.
    
    Args:
        company_id: ID удаляемой компании
        initiated_by_user_id: ID пользователя, инициировавшего удаление
    
    Returns:
        Dict с результатом удаления
    """
    logger.info(f"Начинаем удаление компании {company_id} (инициатор: {initiated_by_user_id})")
    
    container = get_agents_container()
    company_repo = container.company_repository
    subdomain_repo = container.subdomain_repository
    user_repo = container.user_repository
    
    company = await company_repo.get(company_id)
    if not company:
        logger.warning(f"Компания {company_id} не найдена, возможно уже удалена")
        return {"status": "not_found", "company_id": company_id}
    
    deleted_counts = {
        "storage_keys": 0,
        "variable_keys": 0,
        "users_updated": 0,
    }
    
    company_prefix = f"company:{company_id}:"
    
    # 1. Удаляем данные из service DB (storage)
    service_storage = container.storage
    for prefix in COMPANY_DATA_PREFIXES:
        full_prefix = f"{company_prefix}{prefix}"
        count = await _delete_keys_by_prefix(service_storage, full_prefix, "storage")
        deleted_counts["storage_keys"] += count
        logger.info(f"Удалено {count} ключей с префиксом {full_prefix}")
    
    # 2. Удаляем данные из shared DB (variables)
    shared_storage = container.shared_storage
    for prefix in COMPANY_VARIABLE_PREFIXES:
        full_prefix = f"{company_prefix}{prefix}"
        count = await _delete_keys_by_prefix(shared_storage, full_prefix, "variables")
        deleted_counts["variable_keys"] += count
        logger.info(f"Удалено {count} переменных с префиксом {full_prefix}")
    
    # 3. Удаляем subdomain mapping
    if company.subdomain:
        await subdomain_repo.delete(company.subdomain)
        logger.info(f"Удален subdomain mapping: {company.subdomain}")
    
    # 4. Обновляем пользователей - убираем company_id из их списка компаний
    all_users = await user_repo.list_all(limit=10000)
    for user in all_users:
        if company_id in user.companies:
            del user.companies[company_id]
            
            if user.active_company_id == company_id:
                remaining_companies = list(user.companies.keys())
                user.active_company_id = remaining_companies[0] if remaining_companies else ""
            
            user.updated_at = datetime.now(timezone.utc)
            await user_repo.set(user)
            deleted_counts["users_updated"] += 1
            logger.debug(f"Обновлен пользователь {user.user_id}: удалена компания {company_id}")
    
    logger.info(f"Обновлено {deleted_counts['users_updated']} пользователей")
    
    # 5. Удаляем саму компанию
    await company_repo.delete(company_id)
    logger.info(f"Компания {company_id} удалена")
    
    logger.info(
        f"Удаление компании {company_id} завершено: "
        f"storage_keys={deleted_counts['storage_keys']}, "
        f"variable_keys={deleted_counts['variable_keys']}, "
        f"users_updated={deleted_counts['users_updated']}"
    )
    
    return {
        "status": "deleted",
        "company_id": company_id,
        "company_name": company.name,
        "deleted_counts": deleted_counts,
    }


async def _delete_keys_by_prefix(storage, prefix: str, table_name: str) -> int:
    """
    Удаляет все ключи с указанным префиксом из таблицы.
    
    Args:
        storage: Экземпляр Storage
        prefix: Префикс ключей для удаления
        table_name: Имя таблицы
    
    Returns:
        Количество удаленных ключей
    """
    keys = await storage._list_keys_by_prefix_and_table(prefix, table_name, limit=10000)
    if not keys:
        return 0
    
    deleted_count = 0
    for key in keys:
        success = await storage._delete_with_table(key, table_name)
        if success:
            deleted_count += 1
    
    return deleted_count


