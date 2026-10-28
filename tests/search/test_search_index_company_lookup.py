"""Чтение search index ограничено компанией."""

from datetime import UTC, datetime

import pytest

from core.search.index_models import SearchIndexDefinition


@pytest.mark.asyncio
async def test_find_in_company_returns_own_row_and_hides_other_company(
    app,
    unique_id: str,
) -> None:
    _ = app
    search_index_id = f"idx{unique_id}"[:64]
    owner_company_id = f"co-a-{unique_id}"
    other_company_id = f"co-b-{unique_id}"
    now = datetime.now(UTC)
    _ = await SearchIndexDefinition.create(
        SearchIndexDefinition(
            search_index_id=search_index_id,
            company_id=owner_company_id,
            display_name="Company lookup",
            rag_namespace_id=f"ns-{unique_id}",
            rag_collection_id=f"col-{unique_id}",
            created_at=now,
            updated_at=now,
        )
    )
    found = await SearchIndexDefinition.by_search_index_id(owner_company_id, search_index_id)
    assert found is not None
    assert found.company_id == owner_company_id
    assert await SearchIndexDefinition.by_search_index_id(other_company_id, search_index_id) is None
    assert await SearchIndexDefinition.by_search_index_id(owner_company_id, f"missing-{unique_id}") is None
    with pytest.raises(ValueError, match="company_id cannot be empty"):
        _ = await SearchIndexDefinition.by_search_index_id("", search_index_id)
    with pytest.raises(ValueError, match="search_index_id cannot be empty"):
        _ = await SearchIndexDefinition.by_search_index_id(owner_company_id, "")
    deleted = await SearchIndexDefinition.delete_by_id(search_index_id)
    assert deleted is True
