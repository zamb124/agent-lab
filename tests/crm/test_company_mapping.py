"""Строка связи компании с сущностью CRM."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.crm.models.company_mapping import CompanyMapping

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("crm_di")]


async def test_for_entity_returns_row_or_none(unique_id: str) -> None:
    company_id = f"map-{unique_id}"
    entity_id = f"ent-{unique_id}"
    _ = await CompanyMapping.objects.create(
        instance=CompanyMapping(
            company_id=company_id,
            entity_id=entity_id,
            created_at=datetime.now(UTC),
            is_owner=True,
        )
    )

    found = await CompanyMapping.for_entity(entity_id)
    assert found is not None
    assert found.company_id == company_id
    assert await CompanyMapping.for_entity(f"missing-{unique_id}") is None


async def test_ensure_for_company_inserts_once(unique_id: str) -> None:
    company_id = f"ensure-{unique_id}"
    first_entity_id = f"first-{unique_id}"
    second_entity_id = f"second-{unique_id}"
    await CompanyMapping.ensure_for_company(company_id, first_entity_id)
    await CompanyMapping.ensure_for_company(company_id, second_entity_id)

    stored = await CompanyMapping.get(company_id)
    assert stored is not None
    assert stored.entity_id == first_entity_id
