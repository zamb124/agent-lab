"""
Реестр сервисов для миграций.

Каждый сервис регистрирует свои модели, функцию получения URL и каталог миграции.
"""

from collections.abc import Callable
from dataclasses import dataclass

from core.logging import get_logger

logger = get_logger(__name__)
@dataclass
class ServiceDBConfig:
    """Конфигурация БД сервиса"""

    name: str
    get_db_url: Callable[[], str]
    models_module: str
    migrations_dir: str

_registry: list[ServiceDBConfig] = []

def register_service(
    name: str,
    get_db_url: Callable[[], str],
    models_module: str,
    migrations_dir: str = "",
) -> None:
    """
    Регистрирует сервис в реестре.

    Аргументы:
        name: Имя сервиса (shared, flows, crm, sync, rag)
        get_db_url: Функция, возвращающая URL БД из конфига сервиса
        models_module: Путь к модулю с моделями
        migrations_dir: Каталог ``migrations/<name>`` с файлом миграции
    """
    for svc in _registry:
        if svc.name == name:
            return

    location = migrations_dir or f"migrations/{name}"
    _registry.append(ServiceDBConfig(name, get_db_url, models_module, location))
    logger.debug("db.service_registered", name=name, location=str(location))

def get_all_services() -> list[ServiceDBConfig]:
    """Возвращает все зарегистрированные сервисы."""
    return _registry.copy()

def get_service_by_name(name: str) -> ServiceDBConfig:
    """Возвращает конфиг сервиса по имени или бросает KeyError."""
    for svc in _registry:
        if svc.name == name:
            return svc
    raise KeyError(f"Database service is not registered: {name!r}")

def get_unique_db_urls() -> dict[str, list[str]]:
    """
    Возвращает уникальные URL БД с именами сервисов.

    Возвращает:
        dict: {db_url: [service_names]}
    """
    urls: dict[str, list[str]] = {}

    for svc in _registry:
        url = svc.get_db_url()
        if url not in urls:
            urls[url] = []
        urls[url].append(svc.name)

    return urls

def clear_registry() -> None:
    """Очищает реестр (для тестов)."""
    _registry.clear()
