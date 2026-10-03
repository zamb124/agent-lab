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
