"""Process-cache каталога EntityType: hit только при совпадении revision."""

from __future__ import annotations

import pytest

from apps.crm.models.entity_type import (
    EntityType,
    clear_catalog_cache,
    get_entry,
    invalidate_company,
)


def _type_ids(rows: list[EntityType]) -> set[str]:
    return {row.type_id for row in rows}


@pytest.mark.asyncio
async def test_entity_type_catalog_cache_hit_and_invalidate(crm_di, unique_id) -> None:
    clear_catalog_cache()
    company_id = f"cache_co_{unique_id}"
    namespace = f"ns_{unique_id}"

    first = await EntityType.catalog(
        namespace=namespace,
        company_id=company_id,
    )
    assert first == []

    cached = get_entry(company_id, namespace)
    assert cached is not None
    assert cached[0] == 0
    assert list(cached[1]) == []

    invalidate_company(company_id)
    assert get_entry(company_id, namespace) is None


@pytest.mark.asyncio
async def test_entity_type_catalog_create_visible_after_warm_cache(
    crm_di, unique_id
) -> None:
    clear_catalog_cache()
    company_id = f"cache_co2_{unique_id}"
    namespace = f"ns2_{unique_id}"
    type_id = f"custom_{unique_id}"

    _ = await EntityType.catalog(namespace=namespace, company_id=company_id)
    assert get_entry(company_id, namespace) is not None

    row = EntityType(
        company_id=company_id,
        namespace=namespace,
        type_id=type_id,
        name="Custom",
        is_system=False,
    )
    _ = await EntityType.create(row)
    assert get_entry(company_id, namespace) is None

    listed = await EntityType.catalog(
        namespace=namespace,
        company_id=company_id,
    )
    assert type_id in _type_ids(listed)
    cached = get_entry(company_id, namespace)
    assert cached is not None
    assert cached[0] >= 1
    assert type_id in _type_ids(list(cached[1]))


@pytest.mark.asyncio
async def test_entity_type_catalog_update_visible_after_warm_cache(
    crm_di, unique_id
) -> None:
    clear_catalog_cache()
    company_id = f"cache_upd_{unique_id}"
    namespace = f"ns_upd_{unique_id}"
    type_id = f"upd_{unique_id}"

    _ = await EntityType.create(
        EntityType(
            company_id=company_id,
            namespace=namespace,
            type_id=type_id,
            name="Before",
            is_system=False,
        ),
    )
    warmed = await EntityType.catalog(
        namespace=namespace,
        company_id=company_id,
    )
    assert {row.name for row in warmed if row.type_id == type_id} == {"Before"}

    await EntityType.update_field_patch(
        type_id,
        namespace=namespace,
        company_id=company_id,
        patch={"name": "After"},
    )
    listed = await EntityType.catalog(
        namespace=namespace,
        company_id=company_id,
    )
    assert {row.name for row in listed if row.type_id == type_id} == {"After"}
    with pytest.raises(ValueError, match="entity type update requires fields"):
        await EntityType.update_field_patch(
            type_id,
            namespace=namespace,
            company_id=company_id,
            patch={},
        )


@pytest.mark.asyncio
async def test_entity_type_catalog_delete_visible_after_warm_cache(
    crm_di, unique_id
) -> None:
    clear_catalog_cache()
    company_id = f"cache_del_{unique_id}"
    namespace = f"ns_del_{unique_id}"
    type_id = f"del_{unique_id}"

    _ = await EntityType.create(
        EntityType(
            company_id=company_id,
            namespace=namespace,
            type_id=type_id,
            name="Gone",
            is_system=False,
        ),
    )
    _ = await EntityType.catalog(namespace=namespace, company_id=company_id)

    deleted = await EntityType.delete_by_company_namespace_and_type_id(
        type_id,
        namespace=namespace,
        company_id=company_id,
    )
    assert deleted is True

    listed = await EntityType.catalog(
        namespace=namespace,
        company_id=company_id,
    )
    assert type_id not in _type_ids(listed)


@pytest.mark.asyncio
async def test_entity_type_catalog_clone_appears_in_target_namespace(
    crm_di, unique_id
) -> None:
    clear_catalog_cache()
    company_id = f"cache_cl_{unique_id}"
    source_namespace = f"ns_src_{unique_id}"
    target_namespace = f"ns_dst_{unique_id}"
    type_id = f"cl_{unique_id}"

    _ = await EntityType.create(
        EntityType(
            company_id=company_id,
            namespace=source_namespace,
            type_id=type_id,
            name="Cloned",
            is_system=False,
        ),
    )
    _ = await EntityType.catalog(
        namespace=source_namespace,
        company_id=company_id,
    )
    _ = await EntityType.catalog(
        namespace=target_namespace,
        company_id=company_id,
    )

    cloned = await EntityType.ensure_in_namespace(
        type_id,
        source_namespace=source_namespace,
        target_namespace=target_namespace,
        company_id=company_id,
    )
    assert cloned.namespace == target_namespace
    assert cloned.type_id == type_id

    source_rows = await EntityType.catalog(
        namespace=source_namespace,
        company_id=company_id,
    )
    target_rows = await EntityType.catalog(
        namespace=target_namespace,
        company_id=company_id,
    )
    assert type_id in _type_ids(source_rows)
    assert type_id in _type_ids(target_rows)
