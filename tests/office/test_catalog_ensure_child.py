"""Ensure каталога по названию у родителя: параллельные вызовы не плодят дубликаты."""

from __future__ import annotations

import asyncio

import pytest

from core.documents.catalog import DocumentCatalog

_COMPANY_ID = "system"


@pytest.mark.asyncio
async def test_parallel_ensure_child_catalog_creates_one_catalog(unique_id: str) -> None:
    namespace = f"ns_ensure_{unique_id}"

    results = await asyncio.gather(
        *(
            DocumentCatalog.ensure_child(
                company_id=_COMPANY_ID,
                namespace=namespace,
                parent_catalog_id=None,
                title="Flows",
                owner_user_id="test_user",
            )
            for _ in range(5)
        )
    )

    assert len({catalog.catalog_id for catalog, _created in results}) == 1
    assert [created for _catalog, created in results].count(True) == 1


@pytest.mark.asyncio
async def test_ensure_child_catalog_requires_owner_only_to_create(unique_id: str) -> None:
    namespace = f"ns_ensure_owner_{unique_id}"
    with pytest.raises(ValueError, match="owner_user_id is required"):
        _ = await DocumentCatalog.ensure_child(
            company_id=_COMPANY_ID,
            namespace=namespace,
            parent_catalog_id=None,
            title="Flows",
            owner_user_id="",
        )

    created, was_created = await DocumentCatalog.ensure_child(
        company_id=_COMPANY_ID,
        namespace=namespace,
        parent_catalog_id=None,
        title="Flows",
        owner_user_id="test_user",
    )
    existing, created_again = await DocumentCatalog.ensure_child(
        company_id=_COMPANY_ID,
        namespace=namespace,
        parent_catalog_id=None,
        title="Flows",
        owner_user_id="",
    )

    assert was_created is True
    assert created_again is False
    assert existing.catalog_id == created.catalog_id


@pytest.mark.asyncio
async def test_list_by_title_orders_company_catalogs(unique_id: str) -> None:
    company_id = f"co_title_{unique_id}"
    other_company_id = f"co_other_{unique_id}"
    namespace = f"ns_title_{unique_id}"
    alpha, _created_alpha = await DocumentCatalog.ensure_child(
        company_id=company_id,
        namespace=namespace,
        parent_catalog_id=None,
        title=f"Alpha {unique_id}",
        owner_user_id="test_user",
    )
    beta, _created_beta = await DocumentCatalog.ensure_child(
        company_id=company_id,
        namespace=namespace,
        parent_catalog_id=None,
        title=f"Beta {unique_id}",
        owner_user_id="test_user",
    )
    foreign, _created_foreign = await DocumentCatalog.ensure_child(
        company_id=other_company_id,
        namespace=namespace,
        parent_catalog_id=None,
        title=f"Alpha {unique_id}",
        owner_user_id="test_user",
    )

    found = await DocumentCatalog.list_by_title_asc(company_id, unique_id, 10)
    assert [row.catalog_id for row in found] == [alpha.catalog_id, beta.catalog_id]
    limited = await DocumentCatalog.list_by_title_asc(company_id, "", 1)
    assert [row.catalog_id for row in limited] == [alpha.catalog_id]
    other = await DocumentCatalog.list_by_title_asc(other_company_id, unique_id, 10)
    assert [row.catalog_id for row in other] == [foreign.catalog_id]
