from __future__ import annotations

import asyncio

import pytest

from core.models.identity_models import Company


@pytest.mark.asyncio
async def test_put_member_roles_keeps_concurrent_members(container, unique_id: str) -> None:
    company_id = f"co-members-{unique_id}"
    first_user_id = f"mem-a-{unique_id}"
    second_user_id = f"mem-b-{unique_id}"
    repo = container.company_repository
    _ = await repo.set(
        Company(
            company_id=company_id,
            name=f"Members {unique_id}",
            subdomain=f"mem-{unique_id}",
            members={},
        )
    )
    try:
        await asyncio.gather(
            repo.put_member_roles(company_id, first_user_id, ["member"]),
            repo.put_member_roles(company_id, second_user_id, ["admin"]),
        )
        stored = await repo.get(company_id)
        assert stored is not None
        assert stored.members[first_user_id] == ["member"]
        assert stored.members[second_user_id] == ["admin"]
    finally:
        deleted = await repo.delete(company_id)
        if not deleted:
            raise RuntimeError(f"failed to delete company {company_id}")
