"""
Конфигурация Wiki Service.

Отдельных настроек у сервиса нет: URL БД берётся из `database.wiki_url`,
адреса соседей — из `server.*_service_url`.
"""

from core.config import BaseSettings


class WikiSettings(BaseSettings):
    """Настройки сервиса базы знаний."""
