"""Фикстуры клиентских тестов (tests/core/clients)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio

from apps.flows.di import FlowsDi
from core.billing import set_billing_service
from tests.fixtures.service_processes import ServiceProcesses


@pytest_asyncio.fixture(scope="session")
async def llm_billing_service(
    service_processes: ServiceProcesses, setup_database_before_tests: None
) -> AsyncIterator[None]:
    """Глобальный BillingService из FlowsDi для production-пути LLM.

    ``_production_llm_env`` выключает testing-режим: billing идёт через
    ``get_billing_service()`` — без открытого DI глобаль пуста и вызов падает.
    Применять через ``@pytest.mark.usefixtures("llm_billing_service")``.
    """
    _ = setup_database_before_tests
    di = await service_processes.di(FlowsDi)
    set_billing_service(di.billing_service)
    yield
