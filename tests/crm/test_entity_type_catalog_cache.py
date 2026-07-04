"""Request-scope кэш каталога EntityType."""

from __future__ import annotations

import pytest

from apps.crm.db import entity_type_catalog_cache
from apps.crm.db.models import EntityType


@pytest.mark.asyncio
async def test_entity_type_catalog_cache_hit_and_invalidate(crm_container, unique_id) -> None:
    entity_type_catalog_cache.clear_catalog_cache()
    repo = crm_container.entity_type_repository
    company_id = f"cache_co_{unique_id}"
    namespace = f"ns_{unique_id}"

    first = await repo.load_all_entity_types_for_company(
        namespace=namespace,
        company_id=company_id,
    )
    assert first == []

    cached = entity_type_catalog_cache.get_cached(company_id, namespace)
    assert cached is not None
    assert cached == []

    entity_type_catalog_cache.invalidate_company(company_id)
    assert entity_type_catalog_cache.get_cached(company_id, namespace) is None


@pytest.mark.asyncio
async def test_entity_type_catalog_cache_invalidated_on_create(crm_container, unique_id) -> None:
    entity_type_catalog_cache.clear_catalog_cache()
    repo = crm_container.entity_type_repository
    company_id = f"cache_co2_{unique_id}"
    namespace = f"ns2_{unique_id}"

    _ = await repo.load_all_entity_types_for_company(namespace=namespace, company_id=company_id)
    assert entity_type_catalog_cache.get_cached(company_id, namespace) is not None

    row = EntityType(
        company_id=company_id,
        namespace=namespace,
        type_id=f"custom_{unique_id}",
        name="Custom",
        is_system=False,
    )
    _ = await repo.create_custom_type(row, company_id=company_id)
    assert entity_type_catalog_cache.get_cached(company_id, namespace) is None
