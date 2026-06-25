"""
Фикстуры для тестов unified file API.
"""

import pytest_asyncio


@pytest_asyncio.fixture
async def file_db_clean(app):
    """
    Очищает shared DB FileRecord-записи между тестами.

    Для большинства тестов не нужна — file_id уникален для каждого теста.
    """
    from apps.frontend.container import get_frontend_container
    from sqlalchemy import delete, select

    container = get_frontend_container()
    storage = container.file_repository._storage
    async with storage.get_session() as session:
        table = storage._get_table("storage")
        keys_result = await session.execute(
            select(table.c["key"]).where(table.c["key"].like("file:%"))
        )
        keys = [row[0] for row in keys_result]
        if keys:
            await session.execute(delete(table).where(table.c["key"].in_(keys)))
        await session.commit()
    yield
