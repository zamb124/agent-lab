"""Offset-страница шаблонов пространства одной компании."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.crm.models.namespace_template import NamespaceTemplate

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("crm_di")]


async def test_by_template_id_returns_row_or_none(unique_id: str) -> None:
    company_id = f"tpl-by-{unique_id}"
    template_id = f"id-{unique_id}"
    _ = await NamespaceTemplate.create(
        NamespaceTemplate(
            template_key=f"key-{unique_id}",
            company_id=company_id,
            template_id=template_id,
            name="Template",
        )
    )

    found = await NamespaceTemplate.by_template_id(company_id, template_id)
    assert found is not None
    assert found.template_key == f"key-{unique_id}"
    assert await NamespaceTemplate.by_template_id(company_id, f"missing-{unique_id}") is None
    assert await NamespaceTemplate.by_template_id(f"other-{unique_id}", template_id) is None


async def test_page_for_company_orders_newest_first_and_skips_other_company(unique_id: str) -> None:
    company_id = f"tpl-page-{unique_id}"
    other_company_id = f"tpl-page-other-{unique_id}"
    older = datetime(2024, 1, 1, tzinfo=UTC)
    newer = older + timedelta(days=1)
    same_moment_low = f"a-{unique_id}"
    same_moment_high = f"z-{unique_id}"
    _ = await NamespaceTemplate.create(
        NamespaceTemplate(
            template_key=f"old-{unique_id}",
            company_id=company_id,
            template_id=f"old-{unique_id}",
            name="Old",
            created_at=older,
        )
    )
    _ = await NamespaceTemplate.create(
        NamespaceTemplate(
            template_key=same_moment_low,
            company_id=company_id,
            template_id=same_moment_low,
            name="Low",
            created_at=newer,
        )
    )
    _ = await NamespaceTemplate.create(
        NamespaceTemplate(
            template_key=same_moment_high,
            company_id=company_id,
            template_id=same_moment_high,
            name="High",
            created_at=newer,
        )
    )
    _ = await NamespaceTemplate.create(
        NamespaceTemplate(
            template_key=f"foreign-{unique_id}",
            company_id=other_company_id,
            template_id=f"foreign-{unique_id}",
            name="Foreign",
            created_at=newer + timedelta(days=1),
        )
    )

    first = await NamespaceTemplate.page_for_company(company_id, limit=2, offset=0)
    assert first.total == 3
    assert first.limit == 2
    assert first.offset == 0
    assert [item.template_key for item in first.items] == [same_moment_high, same_moment_low]

    second = await NamespaceTemplate.page_for_company(company_id, limit=2, offset=2)
    assert second.total == 3
    assert [item.template_key for item in second.items] == [f"old-{unique_id}"]

    empty = await NamespaceTemplate.page_for_company(f"missing-{unique_id}", limit=10, offset=0)
    assert empty.items == []
    assert empty.total == 0

    with pytest.raises(ValueError, match="limit must be >= 1"):
        _ = await NamespaceTemplate.page_for_company(company_id, limit=0, offset=0)
    with pytest.raises(ValueError, match="offset must be >= 0"):
        _ = await NamespaceTemplate.page_for_company(company_id, limit=1, offset=-1)
