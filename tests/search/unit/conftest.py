"""Unit-тесты search без PostgreSQL / session-инфры."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_database_before_tests():
    yield


@pytest.fixture(scope="session", autouse=True)
def platform_notification_manager_redis(setup_database_before_tests):
    _ = setup_database_before_tests
    yield
