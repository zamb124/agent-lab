"""Активный API-ключ по key_hash."""

from __future__ import annotations

import pytest

from core.models.api_key import ApiKeyRecord


@pytest.mark.asyncio
async def test_active_by_hash_hides_revoked_and_missing(unique_id: str) -> None:
    company_id = f"co_key_{unique_id}"
    created_by = f"user_{unique_id}"
    active = ApiKeyRecord(
        key_id=f"key_{unique_id}",
        company_id=company_id,
        name="active",
        key_hash=f"hash_active_{unique_id}",
        key_prefix="hum_test",
        created_by=created_by,
    )
    revoked = ApiKeyRecord(
        key_id=f"rev_{unique_id}",
        company_id=company_id,
        name="revoked",
        key_hash=f"hash_revoked_{unique_id}",
        key_prefix="hum_test",
        created_by=created_by,
        revoked=True,
    )
    _ = await ApiKeyRecord.set(active)
    _ = await ApiKeyRecord.set(revoked)

    found = await ApiKeyRecord.active_by_hash(active.key_hash)
    assert found is not None
    assert found.key_id == active.key_id
    assert await ApiKeyRecord.active_by_hash(revoked.key_hash) is None
    assert await ApiKeyRecord.active_by_hash(f"missing_{unique_id}") is None
