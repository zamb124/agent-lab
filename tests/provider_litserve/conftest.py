"""Парсеры и чистые юнит-проверки provider_litserve без docker-compose-test (Postgres/Redis).

Корневой ``tests/conftest.py`` поднимает БД и Redis Pub/Sub session-wide; здесь те же
имена фикстур переопределены для деревьев только под ``tests/provider_litserve/``.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_database_before_tests():
    yield


@pytest.fixture(scope="session", autouse=True)
def platform_notification_manager_redis(setup_database_before_tests):
    _ = setup_database_before_tests
    yield
