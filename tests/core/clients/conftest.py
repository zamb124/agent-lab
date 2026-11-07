"""Фикстуры клиентских тестов (tests/core/clients)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio

from apps.flows.di import FlowsDi
from core.billing.service import BillingService
from tests.fixtures.service_processes import ServiceProcesses


@pytest_asyncio.fixture(scope="session")
async def llm_billing_service(
    service_processes: ServiceProcesses, setup_database_before_tests: None
) -> AsyncIterator[BillingService]:
    """BillingService из FlowsDi для production-пути LLM без process-global.

    ``_production_llm_env`` выключает testing-режим: LLMClient требует явный
    ``billing_service``. Применять через
    ``@pytest.mark.usefixtures("llm_billing_service")`` или как аргумент фикстуры.
    """
    _ = setup_database_before_tests
    di = await service_processes.di(FlowsDi)
    yield di.billing_service
