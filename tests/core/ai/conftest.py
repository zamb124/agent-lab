"""Offline AI scoring / catalog fixture tests — без PostgreSQL / Redis / MinIO.

`test-static` гоняет `test_platform_model_scoring_fixtures.py` до `test-up`.
Корневой autouse `setup_database_before_tests` иначе валит gate при недоступной
тестовой БД. Паттерн как в `tests/clients/conftest.py` / `tests/utils/conftest.py`.
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


@pytest.fixture(scope="session", autouse=True)
def ensure_minio_bucket():
    yield
