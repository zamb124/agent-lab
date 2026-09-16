from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apps.guest_runtime.services.lease_store import GuestLeaseStore
from core.config.models import GuestRuntimeFarmConfig
from core.guest_runtime.models import GuestExecutorKind, GuestInvokeKind, GuestLease


def _lease(
    *,
    unique_id: str,
    started_at: datetime,
    last_completed_at: datetime | None,
    in_flight: int,
) -> GuestLease:
    return GuestLease(
        guest_lease_id=f"lease-ttl-{unique_id}",
        company_id=f"co_ttl_{unique_id}",
        user_id=f"user_ttl_{unique_id}",
        flow_id=f"flow_ttl_{unique_id}",
        node_id="agent",
        image_digest=f"inprocess:{unique_id}",
        invoke_kind=GuestInvokeKind.CLI,
        invoke_argv=["python", "main.py"],
        started_at=started_at,
        last_completed_at=last_completed_at,
        in_flight=in_flight,
        idle_ttl_seconds=60,
        executor=GuestExecutorKind.INPROCESS,
        shim_url="http://127.0.0.1:9/shim",
    )


@pytest.mark.asyncio
async def test_remaining_ttl_idle_vs_in_flight(
    guest_lease_store: tuple[GuestLeaseStore, list[GuestLease]],
    unique_id: str,
) -> None:
    store, _held = guest_lease_store
    now = datetime.now(timezone.utc)
    idle = store.remaining_ttl(
        _lease(
            unique_id=f"{unique_id}_idle",
            started_at=now,
            last_completed_at=now,
            in_flight=0,
        )
    )
    assert 86300 <= idle <= 86400
    in_flight = store.remaining_ttl(
        _lease(
            unique_id=f"{unique_id}_flight",
            started_at=now,
            last_completed_at=now,
            in_flight=1,
        )
    )
    assert 86300 <= in_flight <= 86400


@pytest.mark.asyncio
async def test_remaining_ttl_lifetime_expired_raises(
    guest_lease_store: tuple[GuestLeaseStore, list[GuestLease]],
    unique_id: str,
) -> None:
    store, _held = guest_lease_store
    past = datetime.now(timezone.utc) - timedelta(seconds=86401)
    with pytest.raises(RuntimeError, match="TTL already expired"):
        store.remaining_ttl(
            _lease(
                unique_id=unique_id,
                started_at=past,
                last_completed_at=past,
                in_flight=0,
            )
        )


@pytest.mark.asyncio
async def test_remaining_ttl_lifetime_expired_while_in_flight_raises(
    guest_lease_store: tuple[GuestLeaseStore, list[GuestLease]],
    unique_id: str,
) -> None:
    store, _held = guest_lease_store
    past = datetime.now(timezone.utc) - timedelta(seconds=86401)
    with pytest.raises(RuntimeError, match="lifetime expired while in-flight"):
        store.remaining_ttl(
            _lease(
                unique_id=unique_id,
                started_at=past,
                last_completed_at=None,
                in_flight=1,
            )
        )


def test_farm_idle_and_lifetime_defaults() -> None:
    farm = GuestRuntimeFarmConfig()
    assert farm.idle_ttl_seconds == 60
    assert farm.max_lifetime_seconds == 86400
    assert farm.max_leases_per_company == 2
