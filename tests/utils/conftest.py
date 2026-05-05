"""Тесты утилит без PostgreSQL / session-инфры.

Переопределяет ``setup_database_before_tests`` из корневого ``tests/conftest.py``;
см. ``tests/clients/conftest.py``.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_database_before_tests():
    yield


@pytest.fixture
def unique_id() -> str:
    return uuid.uuid4().hex[:12]
