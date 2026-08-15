"""Offline AI scoring / catalog fixture tests — без PostgreSQL / Redis / MinIO / OpenFGA.

`test-static` гоняет `test_platform_model_scoring_fixtures.py` до `test-up`.
Корневые session autouse (`setup_database_before_tests`, Redis notify,
MinIO, `ensure_default_test_user_authz` → OpenFGA) иначе виснут / валят gate.
Паттерн как в `tests/clients/conftest.py` / `tests/utils/conftest.py`.
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


@pytest.fixture(scope="session", autouse=True)
def ensure_default_test_user_authz():
    """Не dual-write в OpenFGA: offline fixtures без store."""
    yield
