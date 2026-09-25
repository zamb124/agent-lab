"""DI capability-gateway из lifespan приложения."""

from __future__ import annotations

import pytest_asyncio
from fastapi import FastAPI

from apps.capability_gateway.di import CapabilityGatewayDi
from core.di import require_di
from tests.fixtures.service_processes import ServiceProcesses


@pytest_asyncio.fixture
async def capability_gateway_app(service_processes: ServiceProcesses) -> FastAPI:
    return await service_processes.app("capability_gateway")


@pytest_asyncio.fixture
async def capability_gateway_di(capability_gateway_app: FastAPI) -> CapabilityGatewayDi:
    return require_di(capability_gateway_app, CapabilityGatewayDi)
