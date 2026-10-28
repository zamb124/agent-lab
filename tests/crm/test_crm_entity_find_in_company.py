"""Чтение CRMEntity по компании и entity_id."""

from __future__ import annotations

import base64
from datetime import UTC, date, datetime, timedelta

import pytest

from apps.crm.models.crm_entity import CRMEntity
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User, UserStatus
from core.types import JsonObject


@pytest.mark.asyncio
async def test_find_in_company_hides_other_company(unique_id: str) -> None:
    company_id = f"ent-co-{unique_id}"
    other_company_id = f"ent-other-{unique_id}"
    entity_id = f"ent-{unique_id}"
    created = await CRMEntity.create(
        CRMEntity(
            entity_id=entity_id,
            company_id=company_id,
            entity_type="note",
            name=f"Note {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    found = await CRMEntity.by_entity_id(company_id, entity_id)
    assert found is not None
    assert found.entity_id == created.entity_id
    assert await CRMEntity.by_entity_id(other_company_id, entity_id) is None
    assert await CRMEntity.by_entity_id(company_id, f"missing-{unique_id}") is None
    with pytest.raises(ValueError, match="company_id cannot be empty"):
        _ = await CRMEntity.by_entity_id("", entity_id)
    with pytest.raises(ValueError, match="entity_id cannot be empty"):
        _ = await CRMEntity.by_entity_id(company_id, "")
    removed = await CRMEntity.delete_returning(entity_id)
    assert removed is not None
    assert removed.entity_id == created.entity_id
    assert await CRMEntity.delete_returning(entity_id) is None
    assert await CRMEntity.get(entity_id) is None


def _bind(company_id: str) -> None:
    user = User(
        user_id=f"user-{company_id}",
        name="CRM",
        status=UserStatus.ACTIVE,
        companies={company_id: ["owner"]},
        active_company_id=company_id,
    )
    company = Company(
        company_id=company_id,
        name=company_id,
        subdomain=company_id[:32],
        owner_user_id=user.user_id,
    )
    _ = set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="test",
        )
    )


@pytest.mark.asyncio
async def test_update_attributes_replaces_json_and_keeps_name(unique_id: str) -> None:
    company_id = f"ent-attr-{unique_id}"
    other_company_id = f"ent-attr-other-{unique_id}"
    entity_id = f"ent-attr-id-{unique_id}"
    _bind(company_id)
    try:
        _ = await CRMEntity.create(
            CRMEntity(
                entity_id=entity_id,
                company_id=company_id,
                entity_type="note",
                name=f"Keep {unique_id}",
                user_id=f"user-{unique_id}",
                attributes={"old": "gone"},
            )
        )
        stored = await CRMEntity.update_attributes(entity_id, {"fresh": "yes"})
        assert stored.name == f"Keep {unique_id}"
        assert stored.attributes == {"fresh": "yes"}
        _bind(other_company_id)
        with pytest.raises(ValueError, match=f"Entity not found: {entity_id}"):
            _ = await CRMEntity.update_attributes(entity_id, {"stolen": "no"})
        _bind(company_id)
        again = await CRMEntity.by_entity_id(company_id, entity_id)
        assert again is not None
        assert again.attributes == {"fresh": "yes"}
        with pytest.raises(ValueError, match="Entity not found: missing"):
            _ = await CRMEntity.update_attributes("missing", {"x": "y"})
        removed = await CRMEntity.delete_returning(entity_id)
        assert removed is not None
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_update_description_if_current_skips_stale_text(unique_id: str) -> None:
    company_id = f"ent-desc-{unique_id}"
    other_company_id = f"ent-desc-other-{unique_id}"
    entity_id = f"ent-desc-id-{unique_id}"
    _bind(company_id)
    try:
        _ = await CRMEntity.create(
            CRMEntity(
                entity_id=entity_id,
                company_id=company_id,
                entity_type="note",
                name=f"Note {unique_id}",
                user_id=f"user-{unique_id}",
                description="old",
            )
        )
        stale = await CRMEntity.update_description_if_current(
            entity_id,
            expected_description="newer",
            description="stolen",
        )
        assert stale is None
        kept = await CRMEntity.by_entity_id(company_id, entity_id)
        assert kept is not None
        assert kept.description == "old"
        stored = await CRMEntity.update_description_if_current(
            entity_id,
            expected_description="old",
            description="fresh",
        )
        assert stored is not None
        assert stored.description == "fresh"
        assert stored.name == f"Note {unique_id}"
        _bind(other_company_id)
        foreign = await CRMEntity.update_description_if_current(
            entity_id,
            expected_description="fresh",
            description="other",
        )
        assert foreign is None
        _bind(company_id)
        again = await CRMEntity.by_entity_id(company_id, entity_id)
        assert again is not None
        assert again.description == "fresh"
        removed = await CRMEntity.delete_returning(entity_id)
        assert removed is not None
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_list_by_entity_type_and_attribute_keeps_company_and_type(unique_id: str) -> None:
    company_id = f"ent-attr-scan-{unique_id}"
    other_company_id = f"ent-attr-scan-other-{unique_id}"
    marker = f"code-{unique_id}"
    matched_id = f"ent-attr-hit-{unique_id}"
    other_type_id = f"ent-attr-type-{unique_id}"
    other_company_entity_id = f"ent-attr-foreign-{unique_id}"
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=matched_id,
            company_id=company_id,
            entity_type="person",
            name=f"Hit {unique_id}",
            user_id=f"user-{unique_id}",
            attributes={"code": marker},
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=other_type_id,
            company_id=company_id,
            entity_type="note",
            name=f"Note {unique_id}",
            user_id=f"user-{unique_id}",
            attributes={"code": marker},
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=other_company_entity_id,
            company_id=other_company_id,
            entity_type="person",
            name=f"Foreign {unique_id}",
            user_id=f"user-{unique_id}",
            attributes={"code": marker},
        )
    )
    found = await CRMEntity.list_by_entity_type_and_attribute(
        "person",
        "code",
        marker,
        company_id=company_id,
    )
    assert [row.entity_id for row in found] == [matched_id]
    empty = await CRMEntity.list_by_entity_type_and_attribute(
        "person",
        "code",
        f"missing-{unique_id}",
        company_id=company_id,
    )
    assert empty == []
    _bind(company_id)
    try:
        from_context = await CRMEntity.list_by_entity_type_and_attribute(
            "person",
            "code",
            marker,
        )
        assert [row.entity_id for row in from_context] == [matched_id]
    finally:
        clear_context()
    for entity_id in (matched_id, other_type_id, other_company_entity_id):
        removed = await CRMEntity.delete_returning(entity_id)
        assert removed is not None


@pytest.mark.asyncio
async def test_list_by_external_ref_keeps_namespace_and_blank_key(unique_id: str) -> None:
    company_id = f"ent-ref-{unique_id}"
    other_company_id = f"ent-ref-other-{unique_id}"
    namespace = f"ns-{unique_id}"
    source_id = f"src-{unique_id}"
    record_id = f"rec-{unique_id}"
    matched_id = f"ent-ref-hit-{unique_id}"
    other_namespace_id = f"ent-ref-ns-{unique_id}"
    foreign_id = f"ent-ref-foreign-{unique_id}"
    ref_entry: JsonObject = {"record_id": record_id}
    external_refs: JsonObject = {source_id: ref_entry}
    refs: JsonObject = {"external_refs": external_refs}
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=matched_id,
            company_id=company_id,
            namespace=namespace,
            entity_type="lead",
            name=f"Lead {unique_id}",
            user_id=f"user-{unique_id}",
            attributes=refs,
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=other_namespace_id,
            company_id=company_id,
            namespace=f"other-{unique_id}",
            entity_type="lead",
            name=f"Other {unique_id}",
            user_id=f"user-{unique_id}",
            attributes=refs,
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=foreign_id,
            company_id=other_company_id,
            namespace=namespace,
            entity_type="lead",
            name=f"Foreign {unique_id}",
            user_id=f"user-{unique_id}",
            attributes=refs,
        )
    )
    found = await CRMEntity.list_by_namespace_entity_type_and_external_ref(
        company_id=company_id,
        namespace=namespace,
        entity_type="lead",
        source_id=f"  {source_id}  ",
        record_id=record_id,
    )
    assert [row.entity_id for row in found] == [matched_id]
    blank = await CRMEntity.list_by_namespace_entity_type_and_external_ref(
        company_id=company_id,
        namespace=namespace,
        entity_type="lead",
        source_id="   ",
        record_id=record_id,
    )
    assert blank == []
    missing = await CRMEntity.list_by_namespace_entity_type_and_external_ref(
        company_id=company_id,
        namespace=namespace,
        entity_type="lead",
        source_id=source_id,
        record_id=f"missing-{unique_id}",
    )
    assert missing == []
    for entity_id in (matched_id, other_namespace_id, foreign_id):
        removed = await CRMEntity.delete_returning(entity_id)
        assert removed is not None


@pytest.mark.asyncio
async def test_list_by_name_orders_and_hides_other_company(unique_id: str) -> None:
    company_id = f"ent-name-{unique_id}"
    other_company_id = f"ent-name-other-{unique_id}"
    first_id = f"ent-name-a-{unique_id}"
    second_id = f"ent-name-b-{unique_id}"
    foreign_id = f"ent-name-foreign-{unique_id}"
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=second_id,
            company_id=company_id,
            entity_type="person",
            name=f"Bravo {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=first_id,
            company_id=company_id,
            entity_type="person",
            name=f"Alpha {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=foreign_id,
            company_id=other_company_id,
            entity_type="person",
            name=f"Alpha {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    ordered = await CRMEntity.list_by_name(company_id, "", limit=1)
    assert [row.entity_id for row in ordered] == [first_id]
    matched = await CRMEntity.list_by_name(company_id, "alpha", limit=10)
    assert [row.entity_id for row in matched] == [first_id]
    missing = await CRMEntity.list_by_name(company_id, f"missing-{unique_id}", limit=10)
    assert missing == []
    for entity_id in (first_id, second_id, foreign_id):
        removed = await CRMEntity.delete_returning(entity_id)
        assert removed is not None


@pytest.mark.asyncio
async def test_list_by_ids_in_order_keeps_input_and_company(unique_id: str) -> None:
    company_id = f"ent-order-{unique_id}"
    other_company_id = f"ent-order-other-{unique_id}"
    first_id = f"ent-order-a-{unique_id}"
    second_id = f"ent-order-b-{unique_id}"
    foreign_id = f"ent-order-foreign-{unique_id}"
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=first_id,
            company_id=company_id,
            entity_type="person",
            name=f"First {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=second_id,
            company_id=company_id,
            entity_type="person",
            name=f"Second {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=foreign_id,
            company_id=other_company_id,
            entity_type="person",
            name=f"Foreign {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    ordered = await CRMEntity.list_by_ids_in_order(
        [f"  {second_id}", " ", first_id, f"missing-{unique_id}", foreign_id, second_id],
        company_id=company_id,
    )
    assert [row.entity_id for row in ordered] == [second_id, first_id, second_id]
    assert await CRMEntity.list_by_ids_in_order(["", "  "], company_id=company_id) == []
    _bind(company_id)
    try:
        from_context = await CRMEntity.list_by_ids_in_order([first_id])
        assert [row.entity_id for row in from_context] == [first_id]
    finally:
        clear_context()
    for entity_id in (first_id, second_id, foreign_id):
        removed = await CRMEntity.delete_returning(entity_id)
        assert removed is not None


@pytest.mark.asyncio
async def test_list_across_companies_by_ids_ignores_input_order(unique_id: str) -> None:
    company_id = f"ent-ids-{unique_id}"
    other_company_id = f"ent-ids-other-{unique_id}"
    home_id = f"ent-ids-a-{unique_id}"
    foreign_id = f"ent-ids-b-{unique_id}"
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=home_id,
            company_id=company_id,
            entity_type="person",
            name=f"Home {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=foreign_id,
            company_id=other_company_id,
            entity_type="person",
            name=f"Foreign {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    found = await CRMEntity.list_across_companies_by_ids(
        [f"  {foreign_id}", " ", home_id, f"missing-{unique_id}", foreign_id]
    )
    assert {row.entity_id for row in found} == {home_id, foreign_id}
    assert len(found) == 2
    assert await CRMEntity.list_across_companies_by_ids(["", "  "]) == []
    for entity_id in (home_id, foreign_id):
        removed = await CRMEntity.delete_returning(entity_id)
        assert removed is not None


@pytest.mark.asyncio
async def test_update_source_entity_id_counts_company_rows(unique_id: str) -> None:
    company_id = f"ent-src-{unique_id}"
    other_company_id = f"ent-src-other-{unique_id}"
    old_source_id = f"ent-src-old-{unique_id}"
    new_source_id = f"ent-src-new-{unique_id}"
    child_id = f"ent-src-child-{unique_id}"
    other_child_id = f"ent-src-keep-{unique_id}"
    foreign_child_id = f"ent-src-foreign-{unique_id}"
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=child_id,
            company_id=company_id,
            entity_type="note",
            name=f"Child {unique_id}",
            user_id=f"user-{unique_id}",
            source_entity_id=old_source_id,
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=other_child_id,
            company_id=company_id,
            entity_type="note",
            name=f"Keep {unique_id}",
            user_id=f"user-{unique_id}",
            source_entity_id=f"other-{unique_id}",
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=foreign_child_id,
            company_id=other_company_id,
            entity_type="note",
            name=f"Foreign {unique_id}",
            user_id=f"user-{unique_id}",
            source_entity_id=old_source_id,
        )
    )
    with pytest.raises(ValueError, match="old_entity_id and new_entity_id must differ"):
        _ = await CRMEntity.update_source_entity_id(company_id, old_source_id, old_source_id)
    updated = await CRMEntity.update_source_entity_id(company_id, old_source_id, new_source_id)
    assert updated == 1
    child = await CRMEntity.get(child_id)
    assert child is not None
    assert child.source_entity_id == new_source_id
    kept = await CRMEntity.get(other_child_id)
    assert kept is not None
    assert kept.source_entity_id == f"other-{unique_id}"
    foreign = await CRMEntity.get(foreign_child_id)
    assert foreign is not None
    assert foreign.source_entity_id == old_source_id
    assert await CRMEntity.update_source_entity_id(company_id, old_source_id, new_source_id) == 0
    for entity_id in (child_id, other_child_id, foreign_child_id):
        removed = await CRMEntity.delete_returning(entity_id)
        assert removed is not None


@pytest.mark.asyncio
async def test_cursor_page_orders_newest_first_and_hides_other_company(unique_id: str) -> None:
    company_id = f"ent-page-{unique_id}"
    other_company_id = f"ent-page-other-{unique_id}"
    namespace = f"ns-page-{unique_id}"
    older_id = f"ent-page-old-{unique_id}"
    newer_id = f"ent-page-new-{unique_id}"
    foreign_id = f"ent-page-foreign-{unique_id}"
    older_at = datetime(2024, 1, 1, tzinfo=UTC)
    newer_at = older_at + timedelta(days=1)
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=older_id,
            company_id=company_id,
            namespace=namespace,
            entity_type="note",
            name=f"Older {unique_id}",
            user_id=f"user-{unique_id}",
            created_at=older_at,
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=newer_id,
            company_id=company_id,
            namespace=namespace,
            entity_type="note",
            name=f"Newer {unique_id}",
            user_id=f"user-{unique_id}",
            created_at=newer_at,
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=foreign_id,
            company_id=other_company_id,
            namespace=namespace,
            entity_type="note",
            name=f"Foreign {unique_id}",
            user_id=f"user-{unique_id}",
            created_at=newer_at,
        )
    )
    first = await CRMEntity.cursor_page(
        entity_type="note",
        namespace=namespace,
        company_id=company_id,
        limit=1,
    )
    assert [row.entity_id for row in first.items] == [newer_id]
    assert first.has_more is True
    assert first.prev_cursor is None
    assert first.next_cursor is not None
    second = await CRMEntity.cursor_page(
        entity_type="note",
        namespace=namespace,
        company_id=company_id,
        limit=1,
        cursor=first.next_cursor,
    )
    assert [row.entity_id for row in second.items] == [older_id]
    assert second.has_more is False
    bad_cursor = base64.urlsafe_b64encode(b'{"ts": 1, "id": "x"}').decode()
    with pytest.raises(ValueError, match="Cursor payload has invalid shape"):
        _ = await CRMEntity.cursor_page(
            entity_type="note",
            namespace=namespace,
            company_id=company_id,
            cursor=bad_cursor,
        )
    for entity_id in (older_id, newer_id, foreign_id):
        removed = await CRMEntity.delete_returning(entity_id)
        assert removed is not None


@pytest.mark.asyncio
async def test_count_for_filter_keeps_type_and_company(unique_id: str) -> None:
    company_id = f"ent-count-{unique_id}"
    other_company_id = f"ent-count-other-{unique_id}"
    namespace = f"ns-count-{unique_id}"
    note_id = f"ent-count-note-{unique_id}"
    person_id = f"ent-count-person-{unique_id}"
    foreign_id = f"ent-count-foreign-{unique_id}"
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=note_id,
            company_id=company_id,
            namespace=namespace,
            entity_type="note",
            name=f"Note {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=person_id,
            company_id=company_id,
            namespace=namespace,
            entity_type="person",
            name=f"Person {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=foreign_id,
            company_id=other_company_id,
            namespace=namespace,
            entity_type="note",
            name=f"Foreign {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    assert (
        await CRMEntity.count_for_filter(
            entity_type="note",
            namespace=namespace,
            company_id=company_id,
        )
        == 1
    )
    assert (
        await CRMEntity.count_for_filter(
            entity_type="task",
            namespace=namespace,
            company_id=company_id,
        )
        == 0
    )
    for entity_id in (note_id, person_id, foreign_id):
        removed = await CRMEntity.delete_returning(entity_id)
        assert removed is not None


@pytest.mark.asyncio
async def test_created_at_bounds_and_count_span_company_and_type(unique_id: str) -> None:
    company_id = f"ent-bounds-{unique_id}"
    other_company_id = f"ent-bounds-other-{unique_id}"
    namespace = f"ns-bounds-{unique_id}"
    older_id = f"ent-bounds-old-{unique_id}"
    newer_id = f"ent-bounds-new-{unique_id}"
    person_id = f"ent-bounds-person-{unique_id}"
    foreign_id = f"ent-bounds-foreign-{unique_id}"
    older_at = datetime(2024, 2, 1, tzinfo=UTC)
    newer_at = older_at + timedelta(days=3)
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=older_id,
            company_id=company_id,
            namespace=namespace,
            entity_type="note",
            name=f"Older {unique_id}",
            user_id=f"user-{unique_id}",
            created_at=older_at,
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=newer_id,
            company_id=company_id,
            namespace=namespace,
            entity_type="note",
            name=f"Newer {unique_id}",
            user_id=f"user-{unique_id}",
            created_at=newer_at,
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=person_id,
            company_id=company_id,
            namespace=namespace,
            entity_type="person",
            name=f"Person {unique_id}",
            user_id=f"user-{unique_id}",
            created_at=newer_at + timedelta(days=1),
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=foreign_id,
            company_id=other_company_id,
            namespace=namespace,
            entity_type="note",
            name=f"Foreign {unique_id}",
            user_id=f"user-{unique_id}",
            created_at=older_at - timedelta(days=1),
        )
    )
    minimum, maximum, total = await CRMEntity.created_at_bounds_and_count(
        entity_type="note",
        namespace=namespace,
        company_id=company_id,
    )
    assert minimum == older_at
    assert maximum == newer_at
    assert total == 2
    empty_min, empty_max, empty_total = await CRMEntity.created_at_bounds_and_count(
        entity_type="task",
        namespace=namespace,
        company_id=company_id,
    )
    assert empty_min is None
    assert empty_max is None
    assert empty_total == 0
    for entity_id in (older_id, newer_id, person_id, foreign_id):
        removed = await CRMEntity.delete_returning(entity_id)
        assert removed is not None


@pytest.mark.asyncio
async def test_count_for_namespace_excludes_types_and_other_company(unique_id: str) -> None:
    company_id = f"ent-ns-count-{unique_id}"
    other_company_id = f"ent-ns-count-other-{unique_id}"
    namespace = f"ns-count-{unique_id}"
    note_id = f"ent-ns-note-{unique_id}"
    person_id = f"ent-ns-person-{unique_id}"
    foreign_id = f"ent-ns-foreign-{unique_id}"
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=note_id,
            company_id=company_id,
            namespace=namespace,
            entity_type="note",
            name=f"Note {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=person_id,
            company_id=company_id,
            namespace=namespace,
            entity_type="person",
            name=f"Person {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=foreign_id,
            company_id=other_company_id,
            namespace=namespace,
            entity_type="note",
            name=f"Foreign {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    with pytest.raises(ValueError, match="Namespace is required"):
        _ = await CRMEntity.count_for_namespace("", company_id=company_id)
    assert await CRMEntity.count_for_namespace(namespace, company_id=company_id) == 2
    assert (
        await CRMEntity.count_for_namespace(
            namespace,
            company_id=company_id,
            exclude_entity_types={"person"},
        )
        == 1
    )
    assert await CRMEntity.count_for_namespace(f"missing-{unique_id}", company_id=company_id) == 0
    for entity_id in (note_id, person_id, foreign_id):
        removed = await CRMEntity.delete_returning(entity_id)
        assert removed is not None


@pytest.mark.asyncio
async def test_list_entity_type_ids_for_namespace_are_sorted_and_scoped(unique_id: str) -> None:
    company_id = f"ent-types-{unique_id}"
    other_company_id = f"ent-types-other-{unique_id}"
    namespace = f"ns-types-{unique_id}"
    note_id = f"ent-types-note-{unique_id}"
    person_id = f"ent-types-person-{unique_id}"
    foreign_id = f"ent-types-foreign-{unique_id}"
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=note_id,
            company_id=company_id,
            namespace=namespace,
            entity_type="note",
            name=f"Note {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=person_id,
            company_id=company_id,
            namespace=namespace,
            entity_type="person",
            name=f"Person {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=foreign_id,
            company_id=other_company_id,
            namespace=namespace,
            entity_type="task",
            name=f"Foreign {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    with pytest.raises(ValueError, match="Namespace is required"):
        _ = await CRMEntity.list_entity_type_ids_for_namespace("", company_id=company_id)
    assert await CRMEntity.list_entity_type_ids_for_namespace(namespace, company_id=company_id) == [
        "note",
        "person",
    ]
    assert await CRMEntity.list_entity_type_ids_for_namespace(
        namespace,
        company_id=company_id,
        exclude_entity_types={"person"},
    ) == ["note"]
    assert await CRMEntity.list_entity_type_ids_for_namespace(f"missing-{unique_id}", company_id=company_id) == []
    for entity_id in (note_id, person_id, foreign_id):
        removed = await CRMEntity.delete_returning(entity_id)
        assert removed is not None


@pytest.mark.asyncio
async def test_list_fts_ranked_pairs_keeps_company_and_limit(unique_id: str) -> None:
    company_id = f"ent-fts-{unique_id}"
    other_company_id = f"ent-fts-other-{unique_id}"
    token = f"zxq{unique_id.replace('-', '')}"
    home_id = f"ent-fts-home-{unique_id}"
    second_id = f"ent-fts-second-{unique_id}"
    foreign_id = f"ent-fts-foreign-{unique_id}"
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=home_id,
            company_id=company_id,
            entity_type="note",
            name=f"{token} alpha",
            user_id=f"user-{unique_id}",
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=second_id,
            company_id=company_id,
            entity_type="note",
            name=f"{token} beta",
            user_id=f"user-{unique_id}",
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=foreign_id,
            company_id=other_company_id,
            entity_type="note",
            name=f"{token} foreign",
            user_id=f"user-{unique_id}",
        )
    )
    ranked = await CRMEntity.list_fts_ranked_pairs(token, company_id=company_id, limit=1)
    assert len(ranked) == 1
    assert ranked[0][0].company_id == company_id
    assert ranked[0][1] > 0
    missing = await CRMEntity.list_fts_ranked_pairs(f"absent{token}", company_id=company_id, limit=5)
    assert missing == []
    for entity_id in (home_id, second_id, foreign_id):
        removed = await CRMEntity.delete_returning(entity_id)
        assert removed is not None


@pytest.mark.asyncio
async def test_counts_by_type_status_and_month_split_type_and_hide_other_company(unique_id: str) -> None:
    company_id = f"ent-facet-{unique_id}"
    other_company_id = f"ent-facet-other-{unique_id}"
    namespace = f"ns-facet-{unique_id}"
    note_id = f"ent-facet-note-{unique_id}"
    person_id = f"ent-facet-person-{unique_id}"
    foreign_id = f"ent-facet-foreign-{unique_id}"
    created_at = datetime(2024, 6, 15, tzinfo=UTC)
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=note_id,
            company_id=company_id,
            namespace=namespace,
            entity_type="note",
            name=f"Note {unique_id}",
            user_id=f"user-{unique_id}",
            created_at=created_at,
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=person_id,
            company_id=company_id,
            namespace=namespace,
            entity_type="person",
            name=f"Person {unique_id}",
            user_id=f"user-{unique_id}",
            created_at=created_at,
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=foreign_id,
            company_id=other_company_id,
            namespace=namespace,
            entity_type="task",
            name=f"Foreign {unique_id}",
            user_id=f"user-{unique_id}",
            created_at=created_at,
        )
    )
    facets = await CRMEntity.counts_by_type_status_and_month(namespace=namespace, company_id=company_id)
    assert facets["by_type"] == {"note": 1, "person": 1}
    assert facets["by_status"] == {"active": 2}
    assert facets["by_month"] == {"2024-06": 2}
    empty = await CRMEntity.counts_by_type_status_and_month(namespace=f"missing-{unique_id}", company_id=company_id)
    assert empty == {"by_type": {}, "by_status": {}, "by_month": {}}
    for entity_id in (note_id, person_id, foreign_id):
        removed = await CRMEntity.delete_returning(entity_id)
        assert removed is not None


@pytest.mark.asyncio
async def test_ordered_by_created_at_spans_companies(unique_id: str) -> None:
    company_id = f"ent-all-{unique_id}"
    other_company_id = f"ent-all-other-{unique_id}"
    older_id = f"ent-all-old-{unique_id}"
    newer_id = f"ent-all-new-{unique_id}"
    older_at = datetime(2020, 1, 1, tzinfo=UTC)
    newer_at = datetime(2020, 1, 2, tzinfo=UTC)
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=newer_id,
            company_id=other_company_id,
            entity_type="note",
            name=f"Newer {unique_id}",
            user_id=f"user-{unique_id}",
            created_at=newer_at,
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=older_id,
            company_id=company_id,
            entity_type="note",
            name=f"Older {unique_id}",
            user_id=f"user-{unique_id}",
            created_at=older_at,
        )
    )
    rows = await CRMEntity.ordered_by_created_at()
    positions = [row.entity_id for row in rows if row.entity_id in {older_id, newer_id}]
    assert positions == [older_id, newer_id]
    for entity_id in (older_id, newer_id):
        removed = await CRMEntity.delete_returning(entity_id)
        assert removed is not None


@pytest.mark.asyncio
async def test_list_by_ids_and_filters_keeps_requested_company_and_type(unique_id: str) -> None:
    company_id = f"ent-ids-{unique_id}"
    other_company_id = f"ent-ids-other-{unique_id}"
    namespace = f"ns-ids-{unique_id}"
    person_id = f"ent-ids-person-{unique_id}"
    task_id = f"ent-ids-task-{unique_id}"
    foreign_id = f"ent-ids-foreign-{unique_id}"
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=person_id,
            company_id=company_id,
            namespace=namespace,
            entity_type="person",
            name=f"Person {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=task_id,
            company_id=company_id,
            namespace=namespace,
            entity_type="task",
            name=f"Task {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=foreign_id,
            company_id=other_company_id,
            namespace=namespace,
            entity_type="person",
            name=f"Foreign {unique_id}",
            user_id=f"user-{unique_id}",
        )
    )
    people = await CRMEntity.list_by_ids_and_filters(
        company_id=company_id,
        entity_ids=[person_id, task_id, foreign_id],
        entity_type="person",
        entity_subtype=None,
        namespace=namespace,
        filters=None,
        filter_field_types=None,
    )
    assert {row.entity_id for row in people} == {person_id}
    both = await CRMEntity.list_by_ids_and_filters(
        company_id=company_id,
        entity_ids=[person_id, task_id],
        entity_type="",
        entity_subtype="",
        namespace="",
        filters=None,
        filter_field_types=None,
    )
    assert {row.entity_id for row in both} == {person_id, task_id}
    assert await CRMEntity.list_by_ids_and_filters(
        company_id=company_id,
        entity_ids=[],
        entity_type="person",
        entity_subtype=None,
        namespace=namespace,
        filters=None,
        filter_field_types=None,
    ) == []


@pytest.mark.asyncio
async def test_list_note_company_namespace_dates_since_keeps_company_notes(unique_id: str) -> None:
    company_id = f"ent-notes-{unique_id}"
    other_company_id = f"ent-notes-other-{unique_id}"
    namespace = f"ns-notes-{unique_id}"
    since = date(2024, 6, 1)
    earlier = date(2024, 5, 1)
    later = date(2024, 6, 2)
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=f"ent-note-later-{unique_id}",
            company_id=company_id,
            namespace=namespace,
            entity_type="note",
            name=f"Later {unique_id}",
            user_id=f"user-{unique_id}",
            note_date=later,
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=f"ent-note-early-{unique_id}",
            company_id=company_id,
            namespace=namespace,
            entity_type="note",
            name=f"Early {unique_id}",
            user_id=f"user-{unique_id}",
            note_date=earlier,
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=f"ent-note-foreign-{unique_id}",
            company_id=other_company_id,
            namespace=namespace,
            entity_type="note",
            name=f"Foreign {unique_id}",
            user_id=f"user-{unique_id}",
            note_date=later,
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=f"ent-task-{unique_id}",
            company_id=company_id,
            namespace=namespace,
            entity_type="task",
            name=f"Task {unique_id}",
            user_id=f"user-{unique_id}",
            note_date=later,
        )
    )
    found = await CRMEntity.list_note_company_namespace_dates_since(since, company_id)
    assert set(found) == {(company_id, namespace, later)}


@pytest.mark.asyncio
async def test_list_note_company_ids_since_orders_companies(unique_id: str) -> None:
    later_company = f"b-notes-{unique_id}"
    earlier_company = f"a-notes-{unique_id}"
    namespace = f"ns-co-{unique_id}"
    since = date(2024, 6, 1)
    earlier = date(2024, 5, 1)
    later = date(2024, 6, 2)
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=f"ent-b-{unique_id}",
            company_id=later_company,
            namespace=namespace,
            entity_type="note",
            name=f"B {unique_id}",
            user_id=f"user-{unique_id}",
            note_date=later,
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=f"ent-a-{unique_id}",
            company_id=earlier_company,
            namespace=namespace,
            entity_type="note",
            name=f"A {unique_id}",
            user_id=f"user-{unique_id}",
            note_date=later,
        )
    )
    _ = await CRMEntity.create(
        CRMEntity(
            entity_id=f"ent-old-{unique_id}",
            company_id=f"z-old-{unique_id}",
            namespace=namespace,
            entity_type="note",
            name=f"Old {unique_id}",
            user_id=f"user-{unique_id}",
            note_date=earlier,
        )
    )
    found = await CRMEntity.list_note_company_ids_since(since)
    assert [company_id for company_id in found if unique_id in company_id] == [
        earlier_company,
        later_company,
    ]
