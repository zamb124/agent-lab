"""Необязательное чтение комментария и ревизии внутри namespace."""

from datetime import UTC, datetime

import pytest

from apps.wiki.content.prosemirror import empty_document
from apps.wiki.models.comment import WikiComment
from apps.wiki.models.domain import WikiLinkPermission, WikiLinkTargetKind
from apps.wiki.models.page import WikiPage
from apps.wiki.models.page_link import WikiPageLink
from apps.wiki.models.revision import WikiRevision


@pytest.mark.asyncio
async def test_comment_and_revision_in_namespace_are_optional(unique_id: str) -> None:
    company_id = f"co-{unique_id}"
    namespace = f"ns-{unique_id}"
    other_namespace = f"ot-{unique_id}"
    now = datetime(2026, 10, 26, tzinfo=UTC)
    comment_id = f"c-{unique_id}"[:64]
    revision_id = f"r-{unique_id}"[:64]
    page_id = f"p-{unique_id}"[:64]

    comment = await WikiComment.create(
        WikiComment(
            wiki_comment_id=comment_id,
            wiki_page_id=page_id,
            company_id=company_id,
            namespace=namespace,
            author_user_id=f"user-{unique_id}",
            created_at=now,
            updated_at=now,
            body_markdown="note",
        )
    )
    found_comment = await WikiComment.in_namespace(company_id, namespace, comment.wiki_comment_id)
    assert found_comment is not None
    assert found_comment.wiki_comment_id == comment_id
    assert await WikiComment.in_namespace(company_id, other_namespace, comment_id) is None
    assert await WikiComment.in_namespace(company_id, namespace, f"missing-{unique_id}"[:64]) is None

    revision = await WikiRevision.create(
        WikiRevision(
            wiki_revision_id=revision_id,
            wiki_page_id=page_id,
            company_id=company_id,
            namespace=namespace,
            content=empty_document(),
            author_user_id=f"user-{unique_id}",
            created_at=now,
            title="Page",
        )
    )
    found_revision = await WikiRevision.in_namespace(company_id, namespace, revision.wiki_revision_id)
    assert found_revision is not None
    assert found_revision.wiki_revision_id == revision_id
    again = await WikiRevision.in_namespace(company_id, namespace, revision_id)
    assert again is not None
    assert again.wiki_revision_id == found_revision.wiki_revision_id
    assert await WikiRevision.in_namespace(company_id, other_namespace, revision_id) is None
    assert await WikiRevision.in_namespace(company_id, namespace, f"missing-{unique_id}"[:64]) is None

    later = now.replace(hour=18)
    later_comment_id = f"c2-{unique_id}"[:64]
    later_revision_id = f"r2-{unique_id}"[:64]
    _ = await WikiComment.create(
        WikiComment(
            wiki_comment_id=later_comment_id,
            wiki_page_id=page_id,
            company_id=company_id,
            namespace=namespace,
            author_user_id=f"user-{unique_id}",
            created_at=later,
            updated_at=later,
            body_markdown="later",
        )
    )
    comments = await WikiComment.list_for_page(company_id, namespace, page_id)
    assert [row.wiki_comment_id for row in comments] == [comment_id, later_comment_id]
    assert await WikiComment.list_for_page(company_id, other_namespace, page_id) == []
    assert await WikiComment.delete_in_namespace(company_id, other_namespace, later_comment_id) == 0
    assert await WikiComment.delete_in_namespace(company_id, namespace, later_comment_id) == 1
    assert await WikiComment.delete_in_namespace(company_id, namespace, later_comment_id) == 0
    assert await WikiComment.in_namespace(company_id, namespace, later_comment_id) is None

    _ = await WikiRevision.create(
        WikiRevision(
            wiki_revision_id=later_revision_id,
            wiki_page_id=page_id,
            company_id=company_id,
            namespace=namespace,
            content=empty_document(),
            author_user_id=f"user-{unique_id}",
            created_at=later,
            title="Later",
        )
    )
    recent = await WikiRevision.list_recent_for_page(company_id, namespace, page_id, limit=1)
    assert [row.wiki_revision_id for row in recent] == [later_revision_id]
    assert await WikiRevision.list_recent_for_page(company_id, other_namespace, page_id, limit=10) == []

    stored_page = await WikiPage.create(
        WikiPage(
            wiki_page_id=page_id,
            company_id=company_id,
            namespace=namespace,
            root_page_id=page_id,
            content=empty_document(),
            created_by_user_id=f"user-{unique_id}",
            last_edited_by_user_id=f"user-{unique_id}",
            created_at=now,
            updated_at=now,
            title="Page",
        )
    )
    assert await WikiPage.ancestors_toward_root(company_id, namespace, page_id) == []
    assert await WikiPage.ancestors_toward_root(company_id, namespace, f"missing-{unique_id}") == []
    assert [row.wiki_page_id for row in await WikiPage.list_subtree(company_id, namespace, page_id)] == [
        page_id
    ]
    assert await WikiPage.list_subtree(company_id, namespace, f"missing-{unique_id}") == []
    assert await WikiPage.next_position(company_id, namespace, None) == 1
    assert await WikiPage.next_position(company_id, other_namespace, None) == 0
    tree = await WikiPage.tree_summaries(company_id, namespace)
    assert page_id in [item.wiki_page_id for item in tree]
    assert await WikiPage.tree_summaries(company_id, other_namespace) == []
    published = await WikiPage.published_subtree_summaries(company_id, namespace, page_id)
    assert [item.wiki_page_id for item in published] == [page_id]
    stored_page.is_published = False
    _ = await stored_page.save()
    assert await WikiPage.published_subtree_summaries(company_id, namespace, page_id) == []
    stored_page.is_published = True
    _ = await stored_page.save()
    await WikiPage.update_link(
        company_id,
        namespace,
        stored_page.wiki_page_id,
        "hash-1",
        True,
        WikiLinkPermission.EDITOR,
    )
    linked = await WikiPage.objects.filter(
        company_id=company_id,
        namespace=namespace,
        wiki_page_id=page_id,
    ).get_or_none()
    assert linked is not None
    assert linked.link_token_hash == "hash-1"
    assert linked.link_enabled is True
    assert linked.link_permission == WikiLinkPermission.EDITOR
    await WikiPage.update_link(
        company_id,
        namespace,
        stored_page.wiki_page_id,
        None,
        False,
        WikiLinkPermission.VIEWER,
    )
    cleared = await WikiPage.objects.filter(
        company_id=company_id,
        namespace=namespace,
        wiki_page_id=page_id,
    ).get_or_none()
    assert cleared is not None
    assert cleared.link_token_hash is None
    assert cleared.link_enabled is False
    await WikiPage.update_company_visible(company_id, namespace, [page_id], False)
    hidden = await WikiPage.objects.filter(
        company_id=company_id,
        namespace=namespace,
        wiki_page_id=page_id,
    ).get_or_none()
    assert hidden is not None
    assert hidden.company_visible is False
    await WikiPage.update_company_visible(company_id, other_namespace, [page_id], True)
    untouched = await WikiPage.objects.filter(
        company_id=company_id,
        namespace=namespace,
        wiki_page_id=page_id,
    ).get_or_none()
    assert untouched is not None
    assert untouched.company_visible is False
    await WikiPage.update_location(
        company_id=company_id,
        namespace=namespace,
        wiki_page_id=stored_page.wiki_page_id,
        parent_page_id=None,
        root_page_id=page_id,
        position=3,
        updated_at=later,
    )
    moved = await WikiPage.objects.filter(
        company_id=company_id,
        namespace=namespace,
        wiki_page_id=page_id,
    ).get_or_none()
    assert moved is not None
    assert moved.position == 3
    assert moved.root_page_id == page_id
    await WikiPage.update_depth_and_root(
        company_id=company_id,
        namespace=namespace,
        wiki_page_id=page_id,
        depth=2,
        root_page_id=f"root-{unique_id}"[:64],
    )
    deepened = await WikiPage.objects.filter(
        company_id=company_id,
        namespace=namespace,
        wiki_page_id=page_id,
    ).get_or_none()
    assert deepened is not None
    assert deepened.depth == 2
    assert deepened.root_page_id == f"root-{unique_id}"[:64]
    alive_ids = [row.wiki_page_id for row in await WikiPage.alive_by_created_at(limit=None)]
    assert page_id in alive_ids
    alive_by_id = await WikiPage.list_alive(company_id, [page_id, f"missing-{unique_id}"])
    assert [row.wiki_page_id for row in alive_by_id] == [page_id]
    assert await WikiPage.list_alive(company_id, []) == []
    assert await WikiPage.list_alive(f"other-{unique_id}", [page_id]) == []
    with pytest.raises(ValueError, match="limit must be >= 1"):
        _ = await WikiPage.alive_by_created_at(limit=0)
    found_by_title = await WikiPage.list_alive_by_title(company_id, "page", 10)
    assert page_id in [row.wiki_page_id for row in found_by_title]
    assert await WikiPage.list_alive_by_title(f"other-{unique_id}", "page", 10) == []
    assert await WikiPage.list_search_hits(company_id, namespace, "page", 10, []) == []
    await WikiPage.mark_deleted(
        company_id=company_id,
        namespace=namespace,
        wiki_page_ids=[page_id],
        deleted_at=later,
    )
    marked = await WikiPage.objects.filter(
        company_id=company_id,
        namespace=namespace,
        wiki_page_id=page_id,
    ).get_or_none()
    assert marked is not None
    assert marked.deleted_at == later
    assert await WikiPage.list_alive(company_id, [page_id]) == []
    assert await WikiPage.next_position(company_id, namespace, None) == 0
    deleted = await WikiPage.list_deleted(company_id, namespace)
    assert [row.wiki_page_id for row in deleted] == [page_id]
    assert await WikiPage.list_deleted(company_id, other_namespace) == []
    hidden_ids = [row.wiki_page_id for row in await WikiPage.alive_by_created_at(limit=None)]
    assert page_id not in hidden_ids
    await WikiPage.update_deleted_at(
        company_id=company_id,
        namespace=namespace,
        wiki_page_id=page_id,
        deleted_at=None,
    )
    restored = await WikiPage.objects.filter(
        company_id=company_id,
        namespace=namespace,
        wiki_page_id=page_id,
    ).get_or_none()
    assert restored is not None
    assert restored.deleted_at is None
    assert await WikiPage.delete_in_namespace(company_id, other_namespace, stored_page.wiki_page_id) == 0
    assert await WikiPage.delete_in_namespace(company_id, namespace, stored_page.wiki_page_id) == 1
    assert await WikiPage.delete_in_namespace(company_id, namespace, stored_page.wiki_page_id) == 0


def _outgoing(
    *,
    link_id: str,
    company_id: str,
    namespace: str,
    source_page_id: str,
    target_id: str,
    created_at: datetime,
) -> WikiPageLink:
    return WikiPageLink(
        wiki_page_link_id=link_id,
        company_id=company_id,
        namespace=namespace,
        source_page_id=source_page_id,
        target_kind=WikiLinkTargetKind.URL,
        target_id=target_id,
        target_label=target_id,
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_replace_outgoing_replaces_the_source_set(unique_id: str) -> None:
    company_id = f"co-{unique_id}"
    namespace = f"ns-{unique_id}"
    source_page_id = f"src-{unique_id}"[:64]
    other_source_id = f"oth-{unique_id}"[:64]
    now = datetime(2026, 10, 26, tzinfo=UTC)
    first = _outgoing(
        link_id=f"a-{unique_id}"[:64],
        company_id=company_id,
        namespace=namespace,
        source_page_id=source_page_id,
        target_id="https://example.test/a",
        created_at=now,
    )
    second = _outgoing(
        link_id=f"b-{unique_id}"[:64],
        company_id=company_id,
        namespace=namespace,
        source_page_id=source_page_id,
        target_id="https://example.test/b",
        created_at=now,
    )
    other = _outgoing(
        link_id=f"c-{unique_id}"[:64],
        company_id=company_id,
        namespace=namespace,
        source_page_id=other_source_id,
        target_id="https://example.test/c",
        created_at=now,
    )
    await WikiPageLink.replace_outgoing(
        company_id=company_id,
        namespace=namespace,
        source_page_id=source_page_id,
        links=[first, second],
    )
    await WikiPageLink.replace_outgoing(
        company_id=company_id,
        namespace=namespace,
        source_page_id=other_source_id,
        links=[other],
    )
    await WikiPageLink.replace_outgoing(
        company_id=company_id,
        namespace=namespace,
        source_page_id=source_page_id,
        links=[first],
    )
    kept = await WikiPageLink.objects.filter(
        company_id=company_id,
        namespace=namespace,
        source_page_id=source_page_id,
    ).all()
    assert [row.wiki_page_link_id for row in kept] == [first.wiki_page_link_id]
    other_rows = await WikiPageLink.objects.filter(
        company_id=company_id,
        namespace=namespace,
        source_page_id=other_source_id,
    ).all()
    assert [row.wiki_page_link_id for row in other_rows] == [other.wiki_page_link_id]
    incoming = await WikiPageLink.list_for_target(
        company_id,
        WikiLinkTargetKind.URL,
        "https://example.test/c",
    )
    assert [row.wiki_page_link_id for row in incoming] == [other.wiki_page_link_id]
    assert (
        await WikiPageLink.list_for_target(
            company_id,
            WikiLinkTargetKind.URL,
            "https://example.test/missing",
        )
        == []
    )
    await WikiPageLink.replace_outgoing(
        company_id=company_id,
        namespace=namespace,
        source_page_id=source_page_id,
        links=[],
    )
    assert (
        await WikiPageLink.objects.filter(
            company_id=company_id,
            namespace=namespace,
            source_page_id=source_page_id,
        ).all()
        == []
    )


@pytest.mark.asyncio
async def test_move_subtree_bundle_moves_page_and_dependents(unique_id: str) -> None:
    company_id = f"co-{unique_id}"
    source_namespace = f"src-{unique_id}"
    target_namespace = f"dst-{unique_id}"
    page_id = f"p-{unique_id}"[:64]
    root_id = f"root-{unique_id}"[:64]
    now = datetime(2026, 10, 26, tzinfo=UTC)
    await WikiPage.move_subtree_bundle_to_namespace(
        company_id,
        source_namespace,
        target_namespace,
        [],
        root_id,
        1,
        None,
        page_id,
    )
    page = await WikiPage.create(
        WikiPage(
            wiki_page_id=page_id,
            company_id=company_id,
            namespace=source_namespace,
            root_page_id=page_id,
            content=empty_document(),
            created_by_user_id=f"user-{unique_id}",
            last_edited_by_user_id=f"user-{unique_id}",
            created_at=now,
            updated_at=now,
            title="Moved",
            depth=0,
        )
    )
    _ = await WikiComment.create(
        WikiComment(
            wiki_comment_id=f"c-{unique_id}"[:64],
            wiki_page_id=page_id,
            company_id=company_id,
            namespace=source_namespace,
            author_user_id=f"user-{unique_id}",
            created_at=now,
            updated_at=now,
        )
    )
    _ = await WikiRevision.create(
        WikiRevision(
            wiki_revision_id=f"r-{unique_id}"[:64],
            wiki_page_id=page_id,
            company_id=company_id,
            namespace=source_namespace,
            content=empty_document(),
            author_user_id=f"user-{unique_id}",
            created_at=now,
            title="Moved",
        )
    )
    await WikiPage.move_subtree_bundle_to_namespace(
        company_id,
        source_namespace,
        target_namespace,
        [page.wiki_page_id],
        root_id,
        2,
        None,
        page.wiki_page_id,
    )
    moved = await WikiPage.objects.filter(company_id=company_id, wiki_page_id=page_id).get()
    assert moved.namespace == target_namespace
    assert moved.root_page_id == root_id
    assert moved.depth == 2
    assert moved.parent_page_id is None
    comment = await WikiComment.in_namespace(company_id, target_namespace, f"c-{unique_id}"[:64])
    assert comment is not None
    revision = await WikiRevision.in_namespace(company_id, target_namespace, f"r-{unique_id}"[:64])
    assert revision is not None
    assert await WikiComment.in_namespace(company_id, source_namespace, f"c-{unique_id}"[:64]) is None
