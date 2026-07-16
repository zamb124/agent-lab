"""Переопределение integration fixtures для eval unit-тестов."""

from __future__ import annotations

import pytest
import pytest_asyncio


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database_before_tests() -> None:
    yield


@pytest.fixture(autouse=True)
async def reset_index_provider_availability_before_search_test() -> None:
    yield


@pytest_asyncio.fixture(scope="session", autouse=True)
async def ensure_platform_search_worker_prerequisites() -> None:
    yield
