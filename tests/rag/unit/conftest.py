"""Переопределение session-фикстур: контрактные тесты без подготовки общей БД."""

import pytest_asyncio


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database_before_tests():
    """Заглушка вместо глобальной `tests/conftest.py` для каталога `tests/rag/unit/`."""
    yield


@pytest_asyncio.fixture(scope="session", autouse=True)
async def ensure_default_test_user_authz():
    """Без общей БД: пользователи и OpenFGA для test_user не нужны."""
    yield
