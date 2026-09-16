from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from apps.guest_runtime.container import GuestRuntimeContainer, get_guest_runtime_container
from apps.guest_runtime.services.farm_service import GuestFarmService
from apps.guest_runtime.services.lease_store import GuestLeaseStore
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.config.models import GuestRuntimeFarmConfig
from core.guest_runtime.models import GuestLease


@pytest.fixture
def guest_runtime_container() -> GuestRuntimeContainer:
    return get_guest_runtime_container()


@pytest.fixture
async def guest_farm_service(
    guest_runtime_container: GuestRuntimeContainer,
) -> AsyncIterator[tuple[GuestFarmService, list[tuple[str, str]]]]:
    await guest_runtime_container.redis_client.connect()
    if not await guest_runtime_container.redis_client.ping():
        raise RuntimeError("guest farm tests require Redis")
    farm = guest_runtime_container.farm_service
    held: list[tuple[str, str]] = []
    yield farm, held
    for flow_id, node_id in held:
        await farm.drop_runtime(flow_id, node_id)


@pytest.fixture
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
