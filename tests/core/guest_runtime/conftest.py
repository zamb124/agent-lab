"""Offline mapping of farm ConnectError — без PostgreSQL / Redis / OpenFGA."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_database_before_tests():
    yield


@pytest.fixture(scope="session", autouse=True)
def ensure_minio_bucket():
    yield


@pytest.fixture(scope="session", autouse=True)
def ensure_default_test_user_authz():
    yield
