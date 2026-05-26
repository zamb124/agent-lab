import pytest

from apps.search.services.provider_availability import ProviderAvailabilityStore
from core.clients.redis_client import RedisClient
from core.config import get_settings


@pytest.fixture
async def provider_state_store(unique_id):
    client = RedisClient(get_settings().database.redis_url)
    await client.connect()
    store = ProviderAvailabilityStore(
        client,
        key_prefix=f"test:search:providers:{unique_id}",
        available_ttl_seconds=300,
        unavailable_ttl_seconds=300,
    )
    try:
        yield store
    finally:
        await client.close()
