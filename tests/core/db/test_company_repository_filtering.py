from __future__ import annotations

import pytest

from core.models.identity_models import Company


@pytest.mark.asyncio
async def test_company_get_returns_saved_company(unique_id: str) -> None:
    company_id = f"co_list_{unique_id}"
    saved = Company(company_id=company_id, name=f"List {unique_id}")
    _ = await Company.set(saved)

    found = await Company.get(company_id)

    assert found is not None
    assert found.company_id == company_id
    assert found.name == saved.name


@pytest.mark.asyncio
async def test_by_subdomain_returns_own_row(unique_id: str) -> None:
    company_id = f"co_sub_{unique_id}"
    subdomain = f"sub{unique_id}"
    saved = Company(company_id=company_id, name=f"Sub {unique_id}", subdomain=subdomain)
    _ = await Company.set(saved)

    found = await Company.by_subdomain(subdomain)
    assert found is not None
    assert found.company_id == company_id
    assert await Company.by_subdomain(f"missing{unique_id}") is None
    with pytest.raises(ValueError, match="subdomain is required"):
        _ = await Company.by_subdomain("")
