"""Физическое удаление Relationship по компании и relationship_id."""

from __future__ import annotations

import base64
from datetime import UTC, datetime

import pytest
from oxyde.exceptions import UniqueViolationError

from apps.crm.models.relationship import Relationship
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User, UserStatus


async def _edge(company_id: str, relationship_id: str, source: str) -> Relationship:
    row = Relationship(
        relationship_id=relationship_id,
        company_id=company_id,
        source_entity_id=source,
        target_entity_id=f"target-{relationship_id}",
        relationship_type="link",
        namespace="default",
    )
    return await Relationship.create(row)


@pytest.mark.asyncio
async def test_delete_by_company_and_relationship_id_returns_count(unique_id: str) -> None:
    company_id = f"rel-a-{unique_id}"
    other_company_id = f"rel-b-{unique_id}"
    relationship_id = f"edge-{unique_id}"
    own = await _edge(company_id, relationship_id, f"src-{unique_id}")
    other = await _edge(other_company_id, f"other-{unique_id}", f"src-other-{unique_id}")

    assert (
        await Relationship.delete_by_company_and_relationship_id(
            other_company_id,
            own.relationship_id,
        )
        == 0
    )
    assert await Relationship.get(own.relationship_id) is not None
    assert (
        await Relationship.delete_by_company_and_relationship_id(company_id, own.relationship_id)
        == 1
    )
    assert (
        await Relationship.delete_by_company_and_relationship_id(company_id, own.relationship_id)
        == 0
    )
    assert await Relationship.get(own.relationship_id) is None
    assert (
        await Relationship.delete_by_company_and_relationship_id(company_id, f"missing-{unique_id}")
        == 0
    )
    assert (
        await Relationship.delete_by_company_and_relationship_id(
            other_company_id,
            other.relationship_id,
        )
        == 1
    )


@pytest.mark.asyncio
async def test_create_inserts_and_rejects_same_primary_key(unique_id: str) -> None:
    company_id = f"rel-c-{unique_id}"
    relationship_id = f"edge-c-{unique_id}"
    created = await _edge(company_id, relationship_id, f"src-c-{unique_id}")
    assert created.relationship_id == relationship_id
    with pytest.raises(UniqueViolationError):
        _ = await _edge(company_id, relationship_id, f"src-c2-{unique_id}")
    stored = await Relationship.get(relationship_id)
    assert stored is not None
    assert stored.source_entity_id == f"src-c-{unique_id}"
    assert (
        await Relationship.delete_by_company_and_relationship_id(company_id, relationship_id) == 1
    )


@pytest.mark.asyncio
async def test_delete_by_source_and_types_returns_count(unique_id: str) -> None:
    company_id = f"rel-src-{unique_id}"
    other_company_id = f"rel-src-other-{unique_id}"
    source_id = f"note-{unique_id}"
    voice = await _edge(company_id, f"voice-{unique_id}", source_id)
    voice.relationship_type = "voice"
    _ = await voice.save(using="crm")
    context = await _edge(company_id, f"ctx-{unique_id}", source_id)
    context.relationship_type = "context"
    _ = await context.save(using="crm")
    kept = await _edge(company_id, f"kept-{unique_id}", source_id)
    other = await _edge(other_company_id, f"other-src-{unique_id}", source_id)
    other.relationship_type = "voice"
    _ = await other.save(using="crm")

    deleted = await Relationship.delete_by_source_and_types(
        company_id,
        source_id,
        ["voice", "context"],
    )
    assert deleted == 2
    assert (
        await Relationship.delete_by_source_and_types(company_id, source_id, ["voice", "context"])
        == 0
    )
    assert await Relationship.get(kept.relationship_id) is not None
    assert await Relationship.get(other.relationship_id) is not None
    assert await Relationship.get(voice.relationship_id) is None
    assert (
        await Relationship.delete_by_company_and_relationship_id(company_id, kept.relationship_id)
        == 1
    )
    assert (
        await Relationship.delete_by_company_and_relationship_id(
            other_company_id,
            other.relationship_id,
        )
        == 1
    )


@pytest.mark.asyncio
async def test_target_by_source_and_type_returns_one_target(unique_id: str) -> None:
    company_id = f"rel-tgt-{unique_id}"
    other_company_id = f"rel-tgt-other-{unique_id}"
    source_id = f"src-tgt-{unique_id}"
    edge = await _edge(company_id, f"edge-tgt-{unique_id}", source_id)
    assert (
        await Relationship.target_by_source_and_type(company_id, source_id, "link")
        == edge.target_entity_id
    )
    assert (
        await Relationship.target_by_source_and_type(other_company_id, source_id, "link") is None
    )
    assert await Relationship.target_by_source_and_type(company_id, source_id, "other") is None
    assert (
        await Relationship.target_by_source_and_type(company_id, f"missing-{unique_id}", "link")
        is None
    )
    assert (
        await Relationship.delete_by_company_and_relationship_id(company_id, edge.relationship_id)
        == 1
    )


@pytest.mark.asyncio
async def test_by_namespace_source_target_and_type_matches_full_key(unique_id: str) -> None:
    company_id = f"rel-edge-{unique_id}"
    other_company_id = f"rel-edge-other-{unique_id}"
    edge = await _edge(company_id, f"edge-full-{unique_id}", f"src-full-{unique_id}")
    found = await Relationship.by_namespace_source_target_and_type(
        company_id=company_id,
        source_entity_id=edge.source_entity_id,
        target_entity_id=edge.target_entity_id,
        relationship_type=edge.relationship_type,
        namespace=edge.namespace,
    )
    assert found is not None
    assert found.relationship_id == edge.relationship_id
    assert (
        await Relationship.by_namespace_source_target_and_type(
            company_id=other_company_id,
            source_entity_id=edge.source_entity_id,
            target_entity_id=edge.target_entity_id,
            relationship_type=edge.relationship_type,
            namespace=edge.namespace,
        )
        is None
    )
    assert (
        await Relationship.by_namespace_source_target_and_type(
            company_id=company_id,
            source_entity_id=edge.source_entity_id,
            target_entity_id=edge.target_entity_id,
            relationship_type=edge.relationship_type,
            namespace="other",
        )
        is None
    )
    assert (
        await Relationship.delete_by_company_and_relationship_id(company_id, edge.relationship_id)
        == 1
    )


@pytest.mark.asyncio
async def test_touching_includes_both_ends_and_company_filter(unique_id: str) -> None:
    company_id = f"rel-touch-{unique_id}"
    other_company_id = f"rel-touch-other-{unique_id}"
    entity_id = f"ent-{unique_id}"
    outgoing = await _edge(company_id, f"out-{unique_id}", entity_id)
    incoming = await Relationship.create(
        Relationship(
            relationship_id=f"in-{unique_id}",
            company_id=company_id,
            source_entity_id=f"other-src-{unique_id}",
            target_entity_id=entity_id,
            relationship_type="link",
            namespace="default",
        )
    )
    unrelated = await _edge(company_id, f"aside-{unique_id}", f"aside-src-{unique_id}")
    foreign = await Relationship.create(
        Relationship(
            relationship_id=f"foreign-{unique_id}",
            company_id=other_company_id,
            source_entity_id=entity_id,
            target_entity_id=f"foreign-target-{unique_id}",
            relationship_type="link",
            namespace="default",
        )
    )

    touched_ids = {row.relationship_id for row in await Relationship.touching(entity_id).all()}
    assert touched_ids == {
        outgoing.relationship_id,
        incoming.relationship_id,
        foreign.relationship_id,
    }
    company_ids = {
        row.relationship_id
        for row in await Relationship.touching_in_company(entity_id, company_id).all()
    }
    assert company_ids == {outgoing.relationship_id, incoming.relationship_id}
    assert await Relationship.touching(f"missing-{unique_id}").all() == []
    for owner, row in (
        (company_id, outgoing),
        (company_id, incoming),
        (company_id, unrelated),
        (other_company_id, foreign),
    ):
        assert (
            await Relationship.delete_by_company_and_relationship_id(owner, row.relationship_id)
            == 1
        )


def _bind_company(company_id: str) -> None:
    user = User(
        user_id=f"user-{company_id}",
        name="Rel",
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
async def test_ensure_edge_returns_existing_without_update(unique_id: str) -> None:
    company_id = f"rel-ensure-{unique_id}"
    _bind_company(company_id)
    try:
        first = await Relationship.ensure_edge(
            Relationship(
                relationship_id=f"first-{unique_id}",
                company_id=company_id,
                source_entity_id=f"src-{unique_id}",
                target_entity_id=f"tgt-{unique_id}",
                relationship_type="link",
                namespace="default",
                weight=1.0,
            )
        )
        second = await Relationship.ensure_edge(
            Relationship(
                relationship_id=f"second-{unique_id}",
                company_id=company_id,
                source_entity_id=first.source_entity_id,
                target_entity_id=first.target_entity_id,
                relationship_type="link",
                namespace="default",
                weight=9.0,
            )
        )
        assert second.relationship_id == first.relationship_id
        assert second.weight == 1.0
        assert await Relationship.get(f"second-{unique_id}") is None
        assert (
            await Relationship.delete_by_company_and_relationship_id(
                company_id,
                first.relationship_id,
            )
            == 1
        )
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_neighbors_for_entities_groups_both_ends(unique_id: str) -> None:
    company_id = f"rel-nb-{unique_id}"
    other_company_id = f"rel-nb-other-{unique_id}"
    left = f"left-{unique_id}"
    right = f"right-{unique_id}"
    _bind_company(company_id)
    try:
        assert await Relationship.neighbors_for_entities([]) == {}
        link = await Relationship.create(
            Relationship(
                relationship_id=f"nb-link-{unique_id}",
                company_id=company_id,
                source_entity_id=left,
                target_entity_id=right,
                relationship_type="link",
                namespace="default",
            )
        )
        other_type = await Relationship.create(
            Relationship(
                relationship_id=f"nb-other-{unique_id}",
                company_id=company_id,
                source_entity_id=left,
                target_entity_id=f"side-{unique_id}",
                relationship_type="mention",
                namespace="default",
            )
        )
        foreign = await Relationship.create(
            Relationship(
                relationship_id=f"nb-foreign-{unique_id}",
                company_id=other_company_id,
                source_entity_id=left,
                target_entity_id=right,
                relationship_type="link",
                namespace="default",
            )
        )
        grouped = await Relationship.neighbors_for_entities([left, right])
        assert {row.relationship_id for row in grouped[left]} == {
            link.relationship_id,
            other_type.relationship_id,
        }
        assert {row.relationship_id for row in grouped[right]} == {link.relationship_id}
        typed = await Relationship.neighbors_for_entities([left], relationship_types=["link"])
        assert {row.relationship_id for row in typed[left]} == {link.relationship_id}
        crossed = await Relationship.neighbors_for_entities([left], cross_company=True)
        assert foreign.relationship_id in {row.relationship_id for row in crossed[left]}
        for owner, row in (
            (company_id, link),
            (company_id, other_type),
            (other_company_id, foreign),
        ):
            assert (
                await Relationship.delete_by_company_and_relationship_id(owner, row.relationship_id)
                == 1
            )
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_graph_page_orders_by_created_at_and_hides_other_company(unique_id: str) -> None:
    company_id = f"rel-page-{unique_id}"
    other_company_id = f"rel-page-other-{unique_id}"
    older_id = f"page-old-{unique_id}"
    newer_id = f"page-new-{unique_id}"
    _bind_company(company_id)
    try:
        older = await Relationship.create(
            Relationship(
                relationship_id=older_id,
                company_id=company_id,
                source_entity_id=f"src-old-{unique_id}",
                target_entity_id=f"tgt-old-{unique_id}",
                relationship_type="link",
                namespace="default",
                created_at=datetime(2020, 1, 1, tzinfo=UTC),
            )
        )
        newer = await Relationship.create(
            Relationship(
                relationship_id=newer_id,
                company_id=company_id,
                source_entity_id=f"src-new-{unique_id}",
                target_entity_id=f"tgt-new-{unique_id}",
                relationship_type="link",
                namespace="default",
                created_at=datetime(2020, 1, 2, tzinfo=UTC),
            )
        )
        _ = await Relationship.create(
            Relationship(
                relationship_id=f"page-foreign-{unique_id}",
                company_id=other_company_id,
                source_entity_id=f"src-foreign-{unique_id}",
                target_entity_id=f"tgt-foreign-{unique_id}",
                relationship_type="link",
                namespace="default",
                created_at=datetime(2019, 1, 1, tzinfo=UTC),
            )
        )
        first = await Relationship.graph_page(limit=1, cursor=None)
        assert [row.relationship_id for row in first.items] == [older.relationship_id]
        assert first.has_more is True
        assert first.next_cursor is not None
        second = await Relationship.graph_page(limit=1, cursor=first.next_cursor)
        assert [row.relationship_id for row in second.items] == [newer.relationship_id]
        bad_cursor = base64.urlsafe_b64encode(b'{"ts": 1, "id": "x"}').decode()
        with pytest.raises(ValueError, match="relationship graph cursor has invalid shape"):
            _ = await Relationship.graph_page(limit=1, cursor=bad_cursor)
        _bind_company(other_company_id)
        foreign_page = await Relationship.graph_page(limit=10, cursor=None)
        assert [row.relationship_id for row in foreign_page.items] == [f"page-foreign-{unique_id}"]
        _bind_company(company_id)
        assert (
            await Relationship.delete_by_company_and_relationship_id(company_id, older_id) == 1
        )
        assert (
            await Relationship.delete_by_company_and_relationship_id(company_id, newer_id) == 1
        )
        _bind_company(other_company_id)
        assert (
            await Relationship.delete_by_company_and_relationship_id(
                other_company_id,
                f"page-foreign-{unique_id}",
            )
            == 1
        )
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_rewrite_entity_id_updates_both_ends(unique_id: str) -> None:
    company_id = f"rel-rw-{unique_id}"
    other_company_id = f"rel-rw-other-{unique_id}"
    old_id = f"old-{unique_id}"
    new_id = f"new-{unique_id}"
    as_source = await Relationship.create(
        Relationship(
            relationship_id=f"rw-src-{unique_id}",
            company_id=company_id,
            source_entity_id=old_id,
            target_entity_id=f"peer-{unique_id}",
            relationship_type="link",
            namespace="default",
        )
    )
    as_target = await Relationship.create(
        Relationship(
            relationship_id=f"rw-tgt-{unique_id}",
            company_id=company_id,
            source_entity_id=f"peer2-{unique_id}",
            target_entity_id=old_id,
            relationship_type="link",
            namespace="default",
        )
    )
    foreign = await Relationship.create(
        Relationship(
            relationship_id=f"rw-foreign-{unique_id}",
            company_id=other_company_id,
            source_entity_id=old_id,
            target_entity_id=f"peer3-{unique_id}",
            relationship_type="link",
            namespace="default",
        )
    )
    updated = await Relationship.rewrite_entity_id(company_id, old_id, new_id)
    assert updated == 2
    source_row = await Relationship.get(as_source.relationship_id)
    target_row = await Relationship.get(as_target.relationship_id)
    foreign_row = await Relationship.get(foreign.relationship_id)
    assert source_row is not None and source_row.source_entity_id == new_id
    assert target_row is not None and target_row.target_entity_id == new_id
    assert foreign_row is not None and foreign_row.source_entity_id == old_id
    assert await Relationship.rewrite_entity_id(company_id, old_id, new_id) == 0
    with pytest.raises(ValueError, match="old_entity_id and new_entity_id must differ"):
        _ = await Relationship.rewrite_entity_id(company_id, new_id, new_id)
    assert (
        await Relationship.delete_by_company_and_relationship_id(
            company_id,
            as_source.relationship_id,
        )
        == 1
    )
    assert (
        await Relationship.delete_by_company_and_relationship_id(
            company_id,
            as_target.relationship_id,
        )
        == 1
    )
    assert (
        await Relationship.delete_by_company_and_relationship_id(
            other_company_id,
            foreign.relationship_id,
        )
        == 1
    )


@pytest.mark.asyncio
async def test_deduplicate_for_entity_drops_self_loop_and_keeps_edge(unique_id: str) -> None:
    company_id = f"rel-dedup-{unique_id}"
    other_company_id = f"rel-dedup-other-{unique_id}"
    entity_id = f"ent-dedup-{unique_id}"
    _bind_company(company_id)
    try:
        loop = await Relationship.create(
            Relationship(
                relationship_id=f"loop-{unique_id}",
                company_id=company_id,
                source_entity_id=entity_id,
                target_entity_id=entity_id,
                relationship_type="link",
                namespace="default",
            )
        )
        kept = await Relationship.create(
            Relationship(
                relationship_id=f"kept-{unique_id}",
                company_id=company_id,
                source_entity_id=entity_id,
                target_entity_id=f"peer-{unique_id}",
                relationship_type="link",
                namespace="default",
            )
        )
        foreign_loop = await Relationship.create(
            Relationship(
                relationship_id=f"foreign-loop-{unique_id}",
                company_id=other_company_id,
                source_entity_id=entity_id,
                target_entity_id=entity_id,
                relationship_type="link",
                namespace="default",
            )
        )
        await Relationship.deduplicate_for_entity(entity_id)
        assert await Relationship.get(loop.relationship_id) is None
        assert await Relationship.get(kept.relationship_id) is not None
        assert await Relationship.get(foreign_loop.relationship_id) is not None
        await Relationship.deduplicate_for_entity(entity_id)
        assert await Relationship.get(kept.relationship_id) is not None
        assert (
            await Relationship.delete_by_company_and_relationship_id(
                company_id,
                kept.relationship_id,
            )
            == 1
        )
        assert (
            await Relationship.delete_by_company_and_relationship_id(
                other_company_id,
                foreign_loop.relationship_id,
            )
            == 1
        )
    finally:
        clear_context()
