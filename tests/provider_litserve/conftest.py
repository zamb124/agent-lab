"""Парсеры и чистые юнит-проверки provider_litserve без docker-compose-test (Postgres/Redis).

Корневой ``tests/conftest.py`` поднимает БД и Redis Pub/Sub session-wide; здесь те же
имена фикстур переопределены для деревьев только под ``tests/provider_litserve/``.
"""

from __future__ import annotations

import pytest
import pytest_asyncio


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database_before_tests():
    yield


@pytest_asyncio.fixture(scope="session", autouse=True)
async def platform_notification_manager_redis(setup_database_before_tests):
    yield


@pytest.fixture(autouse=True)
def reset_provider_litserve_llm_cache() -> None:
    from apps.provider_litserve.llm.local_causal_lm import reset_local_causal_lm_cache_for_tests

    reset_local_causal_lm_cache_for_tests()
    yield
    reset_local_causal_lm_cache_for_tests()
