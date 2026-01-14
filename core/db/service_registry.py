"""
Реестр сервисов для миграций.

Каждый сервис регистрирует свои модели и функцию получения URL БД.
Это позволяет env.py собирать все уникальные БД и применять миграции к каждой.
"""

import logging
from dataclasses import dataclass
from typing import Callable, List

logger = logging.getLogger(__name__)


@dataclass
class ServiceDBConfig:
    """Конфигурация БД сервиса"""
    
    name: str                          # "agents", "crm", "rag"
    get_db_url: Callable[[], str]      # Функция получения URL из конфига сервиса
    models_module: str                 # "apps.agents.src.db.models"


_registry: List[ServiceDBConfig] = []


def register_service(name: str, get_db_url: Callable[[], str], models_module: str) -> None:
    """
    Регистрирует сервис в реестре.
    
    Args:
        name: Имя сервиса (agents, crm, etc.)
        get_db_url: Функция которая возвращает URL БД из конфига сервиса
        models_module: Путь к модулю с моделями
    """
    # Проверяем что сервис еще не зарегистрирован
    for svc in _registry:
        if svc.name == name:
            return
    
    _registry.append(ServiceDBConfig(name, get_db_url, models_module))
    logger.debug(f"Service '{name}' registered for migrations")


def get_all_services() -> List[ServiceDBConfig]:
    """Возвращает все зарегистрированные сервисы"""
    return _registry.copy()


def get_unique_db_urls() -> dict[str, List[str]]:
    """
    Возвращает уникальные URL БД с именами сервисов.
    
    Returns:
        dict: {db_url: [service_names]}
    """
    urls: dict[str, List[str]] = {}
    
    for svc in _registry:
        try:
            url = svc.get_db_url()
            if url not in urls:
                urls[url] = []
            urls[url].append(svc.name)
        except Exception as e:
            logger.warning(f"Failed to get DB URL for service '{svc.name}': {e}")
    
    return urls


def clear_registry() -> None:
    """Очищает реестр (для тестов)"""
    _registry.clear()
