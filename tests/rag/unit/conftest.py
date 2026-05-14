"""Переопределение session-фикстур: контрактные тесты без подготовки общей БД."""

import pytest_asyncio


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database_before_tests():
    """Заглушка вместо глобальной `tests/conftest.py` для каталога `tests/rag/unit/`."""
    yield
