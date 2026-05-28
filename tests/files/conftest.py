"""
Фикстуры для тестов unified file API.
"""

import pytest_asyncio
from sqlalchemy import text


@pytest_asyncio.fixture
async def file_db_clean(sync_app):
    """
    Очищает shared DB FileRecord-записи между тестами (через прямой SQL в shared_storage).

    Для большинства тестов не нужна — file_id уникален для каждого теста.
    Используется только там где важно чистое начальное состояние shared FileRecord таблицы.
    """
    from apps.sync.container import get_sync_container
    container = get_sync_container()
    storage = container.shared_storage
    async with storage._engine.begin() as conn:  # pyright: ignore[reportAttributeAccessIssue]
        await conn.execute(text("DELETE FROM storage WHERE key LIKE 'file:%'"))
    yield
