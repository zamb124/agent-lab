import pytest


@pytest.mark.asyncio
async def test_provider_availability_store_tracks_provider_state(provider_state_store) -> None:
    assert await provider_state_store.get("tinyfish") is None

    first_failure = await provider_state_store.mark_unavailable("tinyfish", "rate limited")
    assert first_failure.available is False
    assert first_failure.consecutive_failures == 1
    assert first_failure.last_error == "rate limited"

    second_failure = await provider_state_store.mark_unavailable("tinyfish", "still down")
    assert second_failure.available is False
    assert second_failure.consecutive_failures == 2

    unavailable = await provider_state_store.get("tinyfish")
    assert unavailable is not None
    assert unavailable.available is False
    assert unavailable.last_error == "still down"

    available = await provider_state_store.mark_available("tinyfish")
    assert available.available is True
    assert available.consecutive_failures == 0
    assert available.last_error is None

    await provider_state_store.clear("tinyfish")
    assert await provider_state_store.get("tinyfish") is None
