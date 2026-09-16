from __future__ import annotations

import pytest

from apps.guest_runtime.services.lease_store import GuestLeaseStore
from core.guest_runtime.models import GuestLease


@pytest.mark.asyncio
async def test_image_ref_incr_decr_gc(
    guest_lease_store: tuple[GuestLeaseStore, list[GuestLease]],
    unique_id: str,
) -> None:
    store, _held = guest_lease_store
    digest = f"sha256:guest-gc-{unique_id}"
    first = await store.incr_image_ref(digest, ttl_seconds=60)
    assert first == 1
    second = await store.incr_image_ref(digest, ttl_seconds=60)
    assert second == 2
    remaining = await store.decr_image_ref(digest)
    assert remaining == 1
    gone = await store.decr_image_ref(digest)
    assert gone == 0
    leftover = await store.decr_image_ref(digest)
    assert leftover == 0
