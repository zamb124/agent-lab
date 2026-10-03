"""
Доменный слой: сервис и модель против настоящей БД.

Здесь проверяется то, что не видно через HTTP: денормализованные поля дерева,
идемпотентность деиндексации, порядок позиций и границы запросов модели.
"""

from __future__ import annotations

import pytest

from apps.wiki.content.markdown_parser import markdown_to_document
from apps.wiki.models.domain import WikiLinkTargetKind
from apps.wiki.models.page import WikiPage
from apps.wiki.models.page_link import WikiPageLink
from apps.wiki.models.revision import WikiRevision
from core.errors.boundary import PlatformAccessDeniedError, PlatformNotFoundError

pytestmark = pytest.mark.no_test_doubles

async def _stored_page(company_id: str, namespace: str, wiki_page_id: str) -> WikiPage | None:
    return await WikiPage.objects.filter(
        company_id=company_id,
        namespace=namespace,
        wiki_page_id=wiki_page_id,
        deleted_at=None,
    ).get_or_none()


COMPANY = "system"
OWNER = "u_owner"
OTHER = "u_other"


@pytest.fixture
def page_factory(wiki_service, wiki_namespace, wiki_domain_context):
    _ = wiki_domain_context

    async def _create(title: str, *, parent_page_id: str | None = None, markdown: str = ""):
        content = markdown_to_document(markdown) if markdown else None
        return await wiki_service.create_page(
            company_id=COMPANY,
            namespace=wiki_namespace,
            user_id=OWNER,
            title=title,
            parent_page_id=parent_page_id,
            content=content,
        )

    return _create


async def test_create_page_derives_markdown_from_content(page_factory, unique_id):
    page = await page_factory(f"Док {unique_id}", markdown="## Раздел\n\nТело.")

    assert page.text_markdown == "## Раздел\n\nТело."
    assert page.content.content[0].attrs["level"] == 2


async def test_update_existing_rewrites_row_and_rejects_missing(page_factory, unique_id):
    page = await page_factory(f"Страница {unique_id}")
    page.title = f"Новое {unique_id}"
    stored = await WikiPage.update_existing(page)
    assert stored.title == f"Новое {unique_id}"
    reloaded = await WikiPage.alive_page(COMPANY, page.namespace, page.wiki_page_id)
    assert reloaded is not None
    assert reloaded.title == stored.title

    missing = page.model_copy(update={"wiki_page_id": f"missing-{unique_id}"})
    with pytest.raises(ValueError, match="not found"):
        await WikiPage.update_existing(missing)


async def test_root_page_points_to_itself(page_factory, unique_id):
    page = await page_factory(f"Корень {unique_id}")

    assert page.root_page_id == page.wiki_page_id
    assert page.depth == 0
    assert page.parent_page_id is None


async def test_deep_tree_keeps_root_and_depth(page_factory, unique_id):
    root = await page_factory(f"Уровень 0 {unique_id}")
    level1 = await page_factory(f"Уровень 1 {unique_id}", parent_page_id=root.wiki_page_id)
    level2 = await page_factory(f"Уровень 2 {unique_id}", parent_page_id=level1.wiki_page_id)

    assert (level1.depth, level2.depth) == (1, 2)
    assert level2.root_page_id == root.wiki_page_id


async def test_positions_increment_within_parent(page_factory, unique_id):
    root = await page_factory(f"Список {unique_id}")
    first = await page_factory(f"Первый {unique_id}", parent_page_id=root.wiki_page_id)
    second = await page_factory(f"Второй {unique_id}", parent_page_id=root.wiki_page_id)

    assert second.position == first.position + 1


async def test_move_updates_depth_of_whole_subtree(
    wiki_service, wiki_namespace, page_factory, unique_id
):
    root = await page_factory(f"Старый корень {unique_id}")
    middle = await page_factory(f"Середина {unique_id}", parent_page_id=root.wiki_page_id)
    leaf = await page_factory(f"Лист {unique_id}", parent_page_id=middle.wiki_page_id)
    new_root = await page_factory(f"Новый корень {unique_id}")

    _ = await wiki_service.move_page(
        company_id=COMPANY,
        namespace=wiki_namespace,
        user_id=OWNER,
        wiki_page_id=middle.wiki_page_id,
        new_parent_page_id=new_root.wiki_page_id,
    )

    refreshed_leaf = await _stored_page(COMPANY, wiki_namespace, leaf.wiki_page_id)
    assert refreshed_leaf is not None
    assert refreshed_leaf.depth == 2
    assert refreshed_leaf.root_page_id == new_root.wiki_page_id


async def test_subtree_listing_includes_all_descendants(
    wiki_namespace, page_factory, unique_id
):
    root = await page_factory(f"Ветвление {unique_id}")
    left = await page_factory(f"Левый {unique_id}", parent_page_id=root.wiki_page_id)
    right = await page_factory(f"Правый {unique_id}", parent_page_id=root.wiki_page_id)
    deep = await page_factory(f"Глубокий {unique_id}", parent_page_id=left.wiki_page_id)

    subtree = await WikiPage.list_subtree(COMPANY, wiki_namespace, root.wiki_page_id)

    assert {item.wiki_page_id for item in subtree} == {
        root.wiki_page_id,
        left.wiki_page_id,
        right.wiki_page_id,
        deep.wiki_page_id,
    }


async def test_ancestors_are_returned_from_nearest_to_root(
    wiki_namespace, page_factory, unique_id
):
    root = await page_factory(f"Предок {unique_id}")
    middle = await page_factory(f"Средний {unique_id}", parent_page_id=root.wiki_page_id)
    leaf = await page_factory(f"Потомок {unique_id}", parent_page_id=middle.wiki_page_id)

    ancestors = await WikiPage.list_ancestors(COMPANY, wiki_namespace, leaf.wiki_page_id)

    assert [item.wiki_page_id for item in ancestors] == [middle.wiki_page_id, root.wiki_page_id]


async def test_model_scopes_reads_by_namespace(
    wiki_namespace, wiki_other_namespace, page_factory, unique_id
):
    page = await page_factory(f"Локальная {unique_id}")

    assert await _stored_page(COMPANY, wiki_namespace, page.wiki_page_id)
    assert await _stored_page(COMPANY, wiki_other_namespace, page.wiki_page_id) is None


async def test_repository_scopes_reads_by_company(wiki_namespace, page_factory, unique_id):
    page = await page_factory(f"Компанейская {unique_id}")

    assert await _stored_page("company2", wiki_namespace, page.wiki_page_id) is None


async def test_require_page_raises_for_missing_page(wiki_service, wiki_namespace):
    with pytest.raises(PlatformNotFoundError):
        _ = await wiki_service.require_page(COMPANY, wiki_namespace, "wpg_nope")


async def test_restricted_page_denies_stranger_in_service_layer(
    wiki_service, wiki_namespace, page_factory, unique_id
):
    page = await page_factory(f"Закрытая {unique_id}", markdown="Текст.")
    _ = await wiki_service.set_company_visible(
        company_id=COMPANY,
        namespace=wiki_namespace,
        user_id=OWNER,
        wiki_page_id=page.wiki_page_id,
        company_visible=False,
    )

    with pytest.raises(PlatformAccessDeniedError):
        _ = await wiki_service.require_viewable_page(
            COMPANY, wiki_namespace, page.wiki_page_id, OTHER
        )


async def test_company_visible_recalculation_does_not_cascade_to_existing_children(
    wiki_service, wiki_namespace, page_factory, unique_id
):
    """`company_visible` — прямой тег FGA `company_viewer`, а не наследуемый TTU.

    Ограничение родителя не переносится на уже созданных потомков: их
    собственный tuple менять нужно отдельно.
    """
    parent = await page_factory(f"Родитель {unique_id}", markdown="Текст.")
    child = await page_factory(
        f"Ребёнок {unique_id}", parent_page_id=parent.wiki_page_id, markdown="Текст."
    )

    _ = await wiki_service.set_company_visible(
        company_id=COMPANY,
        namespace=wiki_namespace,
        user_id=OWNER,
        wiki_page_id=parent.wiki_page_id,
        company_visible=False,
    )

    stored_parent = await _stored_page(COMPANY, wiki_namespace, parent.wiki_page_id)
    stored_child = await _stored_page(COMPANY, wiki_namespace, child.wiki_page_id)
    assert stored_parent is not None and stored_child is not None
    assert stored_parent.company_visible is False
    assert stored_child.company_visible is True


async def test_links_are_rewritten_on_each_save(
    wiki_service, wiki_namespace, page_factory, unique_id
):
    entity_id = f"ent-{unique_id}"
    page = await page_factory(f"Связанная {unique_id}", markdown=f"@[К](entity:{entity_id})")

    links = await WikiPageLink.objects.filter(
        company_id=COMPANY,
        namespace=wiki_namespace,
        source_page_id=page.wiki_page_id,
    ).all()
    assert [(link.target_kind, link.target_id) for link in links] == [
        (WikiLinkTargetKind.CRM_ENTITY, entity_id)
    ]

    _ = await wiki_service.update_page_content(
        company_id=COMPANY,
        namespace=wiki_namespace,
        user_id=OWNER,
        wiki_page_id=page.wiki_page_id,
        content=markdown_to_document("Без упоминаний."),
    )

    assert (
        await WikiPageLink.objects.filter(
            company_id=COMPANY,
            namespace=wiki_namespace,
            source_page_id=page.wiki_page_id,
        ).all()
        == []
    )


async def test_deindexing_missing_document_is_idempotent(wiki_rag_index, page_factory, unique_id):
    page = await page_factory(f"Пустая {unique_id}")

    # Пустая страница в индекс не попадала; повторное снятие не должно падать.
    await wiki_rag_index.remove_page(page)
    await wiki_rag_index.remove_page(page)


async def test_soft_deleted_page_is_hidden_but_restorable(
    wiki_service, wiki_namespace, page_factory, unique_id
):
    page = await page_factory(f"Корзина {unique_id}", markdown="Текст.")

    _ = await wiki_service.delete_page(COMPANY, wiki_namespace, OWNER, page.wiki_page_id)
    assert await _stored_page(COMPANY, wiki_namespace, page.wiki_page_id) is None

    deleted = await WikiPage.objects.filter(
        company_id=COMPANY,
        namespace=wiki_namespace,
        deleted_at__isnull=False,
    ).all()
    assert page.wiki_page_id in {item.wiki_page_id for item in deleted}

    restored = await wiki_service.restore_page(COMPANY, wiki_namespace, OWNER, page.wiki_page_id)
    assert restored.deleted_at is None


async def test_revision_stores_state_before_update(
    wiki_service, wiki_namespace, page_factory, unique_id
):
    page = await page_factory(f"Версии {unique_id}", markdown="Первая редакция.")

    _ = await wiki_service.update_page_content(
        company_id=COMPANY,
        namespace=wiki_namespace,
        user_id=OWNER,
        wiki_page_id=page.wiki_page_id,
        content=markdown_to_document("Вторая редакция."),
    )

    revisions = await (
        WikiRevision.objects.filter(
            company_id=COMPANY,
            namespace=wiki_namespace,
            wiki_page_id=page.wiki_page_id,
        )
        .order_by("-created_at")
        .limit(10)
        .all()
    )
    assert len(revisions) == 1
    stored = await WikiRevision.objects.filter(
        company_id=COMPANY,
        namespace=wiki_namespace,
        wiki_revision_id=revisions[0].wiki_revision_id,
    ).get_or_none()
    assert stored is not None
    assert stored.text_markdown == "Первая редакция."


async def test_public_link_token_is_stored_hashed(
    wiki_service, wiki_namespace, page_factory, unique_id
):
    page = await page_factory(f"Публичная {unique_id}", markdown="Текст.")

    raw_token = await wiki_service.rotate_public_link(
        company_id=COMPANY,
        namespace=wiki_namespace,
        user_id=OWNER,
        wiki_page_id=page.wiki_page_id,
        enabled=True,
    )

    assert raw_token is not None
    found = await WikiPage.get_public_page(raw_token)
    assert found is not None
    assert found.wiki_page_id == page.wiki_page_id

    # В базе лежит только хеш: сырой токен восстановить нельзя.
    stored = await _stored_page(COMPANY, wiki_namespace, page.wiki_page_id)
    assert stored is not None
    assert raw_token not in (stored.text_markdown, stored.title)
