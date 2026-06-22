"""Сборка BrowserRuntimeFacade для тестов с реальными зависимостями (Redis, S3 file_processor)."""

from __future__ import annotations

from apps.browser.config import get_browser_settings
from apps.browser.engine.types import BrowserRuntimeSettingsView
from apps.browser.orchestration.runtime_facade import BrowserRuntimeFacade
from core.clients.redis_client import RedisClient
from core.context import get_context
from core.db.storage import Storage
from core.files.file_repository import FileRepository
from core.files.processors import FileProcessor


def build_test_facade(view: BrowserRuntimeSettingsView) -> BrowserRuntimeFacade:
    """
    Собрать фасад с теми же зависимостями, что и контейнер: RedisClient для состояния
    сессий и FileProcessor (S3) для артефактов. URL берутся из конфигурации сервиса.
    """
    settings = get_browser_settings()
    redis_url = settings.database.redis_url
    shared_url = settings.database.shared_url
    if not redis_url:
        raise ValueError("database.redis_url обязателен для тестового фасада browser")
    if not shared_url:
        raise ValueError("database.shared_url обязателен для тестового фасада browser")
    redis_client = RedisClient(redis_url)
    storage = Storage(db_url=shared_url, get_context_func=get_context)
    file_processor = FileProcessor(file_repository=FileRepository(storage=storage))
    return BrowserRuntimeFacade(view, redis_client=redis_client, file_processor=file_processor)
