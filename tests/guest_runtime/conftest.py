from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from fastapi import FastAPI

from apps.guest_runtime.di import GuestRuntimeDi
from apps.guest_runtime.services.farm_service import GuestFarmService
from apps.guest_runtime.services.lease_store import GuestLeaseStore
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.config.models import GuestRuntimeFarmConfig
from core.di import require_di
from core.guest_runtime.models import GuestLease


@pytest_asyncio.fixture
async def guest_runtime_app() -> AsyncIterator[FastAPI]:
    from apps.guest_runtime.main import app

    yield app


@pytest_asyncio.fixture
async def guest_runtime_di(
    guest_runtime_app: FastAPI,
    setup_database_before_tests: None,
) -> AsyncIterator[GuestRuntimeDi]:
    _ = setup_database_before_tests
    async with guest_runtime_app.router.lifespan_context(guest_runtime_app):
        yield require_di(guest_runtime_app, GuestRuntimeDi)


@pytest_asyncio.fixture
async def guest_farm_service(
    guest_runtime_di,
) -> AsyncIterator[tuple[GuestFarmService, list[tuple[str, str]]]]:
    if not await guest_runtime_di.redis_client.ping():
        raise RuntimeError("guest farm tests require Redis")
    farm = guest_runtime_di.farm_service
    held: list[tuple[str, str]] = []
    yield farm, held
    for flow_id, node_id in held:
        await farm.drop_runtime(flow_id, node_id)


@pytest_asyncio.fixture
async def guest_lease_store() -> AsyncIterator[tuple[GuestLeaseStore, list[GuestLease]]]:
    redis = RedisClient(get_settings().database.redis_url)
    await redis.connect()
    store = GuestLeaseStore(
        redis,
        GuestRuntimeFarmConfig(max_leases_per_company=2, max_leases_cluster=10_000),
    )
    held: list[GuestLease] = []
    yield store, held
    for lease in held:
        await store.release(lease)
    await redis.close()
