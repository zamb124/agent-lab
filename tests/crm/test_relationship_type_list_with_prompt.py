"""Типы связей компании с непустым prompt."""

from __future__ import annotations

import pytest

from apps.crm.models.relationship_type import RelationshipType


@pytest.mark.asyncio
async def test_list_with_prompt_keeps_empty_string_and_skips_null(unique_id: str) -> None:
    company_id = f"rel-{unique_id}"
    other_company_id = f"rel-other-{unique_id}"
    with_prompt = RelationshipType(
        type_id=f"with-{unique_id}",
        company_id=company_id,
        name="With",
        prompt="text",
    )
    empty_prompt = RelationshipType(
        type_id=f"empty-{unique_id}",
        company_id=company_id,
        name="Empty",
        prompt="",
    )
    null_prompt = RelationshipType(
        type_id=f"null-{unique_id}",
        company_id=company_id,
        name="Null",
        prompt=None,
    )
    foreign = RelationshipType(
        type_id=f"foreign-{unique_id}",
        company_id=other_company_id,
        name="Foreign",
        prompt="text",
    )
    _ = await RelationshipType.objects.create(instance=with_prompt)
    _ = await RelationshipType.objects.create(instance=empty_prompt)
    _ = await RelationshipType.objects.create(instance=null_prompt)
    _ = await RelationshipType.objects.create(instance=foreign)

    found = await RelationshipType.list_unordered_with_prompt(company_id)
    assert {row.type_id for row in found} == {with_prompt.type_id, empty_prompt.type_id}


@pytest.mark.asyncio
async def test_update_loaded_by_company_and_type_id_counts_rows(unique_id: str) -> None:
    company_id = f"rel-upd-{unique_id}"
    stored = await RelationshipType.create(
        RelationshipType(
            type_id=f"t-{unique_id}",
            company_id=company_id,
            name="Before",
            prompt=None,
        )
    )
    stored.name = "After"
    stored.prompt = "now"
    assert await RelationshipType.update_loaded_by_company_and_type_id(stored) == 1
    found = await RelationshipType.list_unordered_with_prompt(company_id)
    assert {row.type_id: row.name for row in found} == {stored.type_id: "After"}
    missing = RelationshipType(
        type_id=f"missing-{unique_id}",
        company_id=company_id,
        name="After",
        prompt="now",
    )
    assert await RelationshipType.update_loaded_by_company_and_type_id(missing) == 0
