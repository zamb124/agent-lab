from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from apps.guest_runtime.services.lease_store import GuestLeaseStore
from core.guest_runtime.models import (
    GuestExecutorKind,
    GuestInvokeKind,
    GuestLease,
    GuestLeaseCapError,
)


def _lease(*, company_id: str, flow_id: str, node_id: str, digest: str) -> GuestLease:
    now = datetime.now(timezone.utc)
    return GuestLease(
        guest_lease_id=f"lease-{flow_id}-{node_id}",
        company_id=company_id,
        user_id="user_guest_cap",
        flow_id=flow_id,
        node_id=node_id,
        image_digest=digest,
        invoke_kind=GuestInvokeKind.CLI,
        invoke_argv=["python", "main.py"],
        started_at=now,
        last_completed_at=now,
        in_flight=0,
        idle_ttl_seconds=60,
        executor=GuestExecutorKind.INPROCESS,
        shim_url="http://127.0.0.1:9/shim",
    )


@pytest.mark.asyncio
async def test_lease_cap_two_per_company(
    guest_lease_store: tuple[GuestLeaseStore, list[GuestLease]],
    unique_id: str,
) -> None:
    store, held = guest_lease_store
    company_id = f"co_guest_cap_{unique_id}"
    digest = f"inprocess:{unique_id}"
    first = _lease(company_id=company_id, flow_id=f"f1_{unique_id}", node_id="n1", digest=digest)
    second = _lease(company_id=company_id, flow_id=f"f2_{unique_id}", node_id="n2", digest=digest)
    third = _lease(company_id=company_id, flow_id=f"f3_{unique_id}", node_id="n3", digest=digest)
    await store.acquire_new(first, ttl_seconds=30)
    held.append(first)
    await store.acquire_new(second, ttl_seconds=30)
    held.append(second)
    with pytest.raises(GuestLeaseCapError):
        await store.acquire_new(third, ttl_seconds=30)


@pytest.mark.asyncio
async def test_lease_cap_rebuilds_after_redis_ttl(
    guest_lease_store: tuple[GuestLeaseStore, list[GuestLease]],
    unique_id: str,
) -> None:
    store, held = guest_lease_store
    company_id = f"co_guest_ttl_cap_{unique_id}"
    digest = f"inprocess:{unique_id}"
    first = _lease(company_id=company_id, flow_id=f"ft1_{unique_id}", node_id="n1", digest=digest)
    second = _lease(company_id=company_id, flow_id=f"ft2_{unique_id}", node_id="n2", digest=digest)
    third = _lease(company_id=company_id, flow_id=f"ft3_{unique_id}", node_id="n3", digest=digest)
    await store.acquire_new(first, ttl_seconds=1)
    held.append(first)
    await store.acquire_new(second, ttl_seconds=1)
    held.append(second)
    deadline = datetime.now(timezone.utc).timestamp() + 3
    while datetime.now(timezone.utc).timestamp() < deadline:
        gone = await store.get(first.flow_id, first.node_id)
        if gone is None:
            break
        await asyncio.sleep(0.05)
    else:
        raise AssertionError("guest lease Redis TTL did not drop the key")
    await store.acquire_new(third, ttl_seconds=30)
    held.append(third)
