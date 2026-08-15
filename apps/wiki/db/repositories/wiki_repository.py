"""
Хранилище страниц wiki, ревизий, участников, ссылок и комментариев.

Изоляция обеспечивается здесь: каждый публичный метод принимает `company_id`
и `namespace` и подставляет их в `WHERE`. Метода «достать страницу по id»
без пары ключей не существует — иначе граница namespace обходилась бы одним
неаккуратным вызовом.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import Select, delete, func, select, update

from apps.wiki.content.prosemirror import ProseMirrorNode
from apps.wiki.db.base import WikiDatabase
from apps.wiki.db.models import (
    WikiCommentRow,
    WikiPageLinkRow,
    WikiPageRow,
    WikiRevisionRow,
)
from apps.wiki.models.domain import (
    WikiBacklink,
    WikiComment,
    WikiLinkPermission,
    WikiLinkTargetKind,
    WikiPage,
    WikiPageLink,
    WikiPageSummary,
    WikiRevision,
    WikiRevisionSummary,
    WikiSearchHit,
)
from core.types import JsonObject, require_json_object


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _content_to_json(content: ProseMirrorNode) -> JsonObject:
    return require_json_object(content.model_dump(mode="json"), "WikiPage.content")


def _content_from_json(raw: JsonObject) -> ProseMirrorNode:
    return ProseMirrorNode.model_validate(raw)


def _row_to_page(row: WikiPageRow) -> WikiPage:
    return WikiPage(
        wiki_page_id=row.wiki_page_id,
        company_id=row.company_id,
        namespace=row.namespace,
        parent_page_id=row.parent_page_id,
        root_page_id=row.root_page_id,
        depth=row.depth,
        position=row.position,
        title=row.title,
        icon=row.icon,
        cover_url=row.cover_url,
        content=_content_from_json(row.content),
        text_markdown=row.text_markdown,
        company_visible=row.company_visible,
        is_published=row.is_published,
        published_at=row.published_at,
        is_template=row.is_template,
        is_full_width=row.is_full_width,
        link_enabled=row.link_enabled,
        link_permission=WikiLinkPermission(row.link_permission),
        created_by_user_id=row.created_by_user_id,
        last_edited_by_user_id=row.last_edited_by_user_id,
        revision_count=row.revision_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


def _row_to_summary(row: WikiPageRow, has_children: bool) -> WikiPageSummary:
    return WikiPageSummary(
        wiki_page_id=row.wiki_page_id,
        namespace=row.namespace,
        parent_page_id=row.parent_page_id,
        root_page_id=row.root_page_id,
        depth=row.depth,
        position=row.position,
        title=row.title,
        icon=row.icon,
        company_visible=row.company_visible,
        is_published=row.is_published,
        is_template=row.is_template,
        has_children=has_children,
        updated_at=row.updated_at,
        last_edited_by_user_id=row.last_edited_by_user_id,
    )


def _row_to_revision(row: WikiRevisionRow) -> WikiRevision:
    return WikiRevision(
        wiki_revision_id=row.wiki_revision_id,
        wiki_page_id=row.wiki_page_id,
        company_id=row.company_id,
        namespace=row.namespace,
        title=row.title,
        content=_content_from_json(row.content),
        text_markdown=row.text_markdown,
        author_user_id=row.author_user_id,
        created_at=row.created_at,
    )


def _row_to_link(row: WikiPageLinkRow) -> WikiPageLink:
    return WikiPageLink(
        wiki_page_link_id=row.wiki_page_link_id,
        company_id=row.company_id,
        namespace=row.namespace,
        source_page_id=row.source_page_id,
        target_kind=WikiLinkTargetKind(row.target_kind),
        target_id=row.target_id,
        target_label=row.target_label,
        created_at=row.created_at,
    )


def _row_to_comment(row: WikiCommentRow) -> WikiComment:
    return WikiComment(
        wiki_comment_id=row.wiki_comment_id,
        wiki_page_id=row.wiki_page_id,
        company_id=row.company_id,
        namespace=row.namespace,
        parent_comment_id=row.parent_comment_id,
        author_user_id=row.author_user_id,
        body_markdown=row.body_markdown,
        anchor_text=row.anchor_text,
        resolved_at=row.resolved_at,
        resolved_by_user_id=row.resolved_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class WikiRepository:
    """CRUD страниц и связанных сущностей в `platform_wiki`."""

    def __init__(self, db: WikiDatabase) -> None:
        self._db: WikiDatabase = db

    # --- страницы ---

    def _alive_pages(self, company_id: str, namespace: str) -> Select[tuple[WikiPageRow]]:
        return select(WikiPageRow).where(
            WikiPageRow.company_id == company_id,
            WikiPageRow.namespace == namespace,
            WikiPageRow.deleted_at.is_(None),
        )

    async def insert_page(self, page: WikiPage) -> WikiPage:
        async with self._db.session() as session:
            row = WikiPageRow(
                wiki_page_id=page.wiki_page_id,
                company_id=page.company_id,
                namespace=page.namespace,
                parent_page_id=page.parent_page_id,
                root_page_id=page.root_page_id,
                depth=page.depth,
                position=page.position,
                title=page.title,
                icon=page.icon,
                cover_url=page.cover_url,
                content=_content_to_json(page.content),
                text_markdown=page.text_markdown,
                company_visible=page.company_visible,
                is_published=page.is_published,
                published_at=page.published_at,
                is_template=page.is_template,
                is_full_width=page.is_full_width,
                link_enabled=page.link_enabled,
                link_permission=page.link_permission.value,
                created_by_user_id=page.created_by_user_id,
                last_edited_by_user_id=page.last_edited_by_user_id,
                revision_count=page.revision_count,
                created_at=page.created_at,
                updated_at=page.updated_at,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _row_to_page(row)

    async def hard_delete_page(
        self, company_id: str, namespace: str, wiki_page_id: str
    ) -> None:
        """Компенсация dual-write: удаляет строку страницы без soft-delete."""
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(WikiPageRow).where(
                        WikiPageRow.company_id == company_id,
                        WikiPageRow.namespace == namespace,
                        WikiPageRow.wiki_page_id == wiki_page_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return
            await session.delete(row)
            await session.commit()

    async def get_page(
        self, company_id: str, namespace: str, wiki_page_id: str
    ) -> WikiPage | None:
        async with self._db.session() as session:
            stmt = self._alive_pages(company_id, namespace).where(
                WikiPageRow.wiki_page_id == wiki_page_id
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _row_to_page(row) if row is not None else None

    async def get_public_page_by_link_token(self, link_token_hash: str) -> WikiPage | None:
        """Страница по хешу публичной ссылки.

        Единственный доступ без namespace: анонимный посетитель его не знает.
        Namespace страницы возвращается вызывающему и дальше используется как
        граница для всех связанных запросов.

        Условия публичной выдачи собраны здесь: включённая ссылка, живая
        страница и `is_published`. Черновик по ссылке не отдаётся.
        """
        async with self._db.session() as session:
            stmt = select(WikiPageRow).where(
                WikiPageRow.link_token_hash == link_token_hash,
                WikiPageRow.link_enabled.is_(True),
                WikiPageRow.is_published.is_(True),
                WikiPageRow.deleted_at.is_(None),
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _row_to_page(row) if row is not None else None

    async def list_tree(self, company_id: str, namespace: str) -> list[WikiPageSummary]:
        """Всё дерево namespace, отсортированное для отрисовки sidebar."""
        async with self._db.session() as session:
            stmt = self._alive_pages(company_id, namespace).order_by(
                WikiPageRow.depth, WikiPageRow.position, WikiPageRow.title
            )
            rows = list((await session.execute(stmt)).scalars().all())
            parents = {row.parent_page_id for row in rows if row.parent_page_id}
            return [_row_to_summary(row, row.wiki_page_id in parents) for row in rows]

    async def list_children(
        self, company_id: str, namespace: str, parent_page_id: str | None
    ) -> list[WikiPageSummary]:
        async with self._db.session() as session:
            stmt = self._alive_pages(company_id, namespace).order_by(
                WikiPageRow.position, WikiPageRow.title
            )
            if parent_page_id is None:
                stmt = stmt.where(WikiPageRow.parent_page_id.is_(None))
            else:
                stmt = stmt.where(WikiPageRow.parent_page_id == parent_page_id)
            rows = list((await session.execute(stmt)).scalars().all())
            child_ids = [row.wiki_page_id for row in rows]
            grandchildren: set[str] = set()
            if child_ids:
                sub_stmt = select(WikiPageRow.parent_page_id).where(
                    WikiPageRow.company_id == company_id,
                    WikiPageRow.namespace == namespace,
                    WikiPageRow.deleted_at.is_(None),
                    WikiPageRow.parent_page_id.in_(child_ids),
                )
                grandchildren = {
                    value
                    for value in (await session.execute(sub_stmt)).scalars().all()
                    if value is not None
                }
            return [_row_to_summary(row, row.wiki_page_id in grandchildren) for row in rows]

    async def list_subtree(
        self, company_id: str, namespace: str, wiki_page_id: str
    ) -> list[WikiPage]:
        """Страница и все её потомки.

        Обход идёт по уровням: дерево wiki неглубокое, рекурсивный CTE здесь
        избыточен и хуже читается.
        """
        async with self._db.session() as session:
            stmt = self._alive_pages(company_id, namespace)
            rows = list((await session.execute(stmt)).scalars().all())

        by_parent: dict[str | None, list[WikiPageRow]] = {}
        for row in rows:
            by_parent.setdefault(row.parent_page_id, []).append(row)

        root = next((row for row in rows if row.wiki_page_id == wiki_page_id), None)
        if root is None:
            return []

        collected: list[WikiPageRow] = [root]
        queue: list[str] = [wiki_page_id]
        while queue:
            current = queue.pop()
            for child in by_parent.get(current, []):
                collected.append(child)
                queue.append(child.wiki_page_id)
        return [_row_to_page(row) for row in collected]

    async def list_public_subtree(
        self, company_id: str, namespace: str, root_page_id: str
    ) -> list[WikiPageSummary]:
        """Опубликованное поддерево — состав публичного сайта.

        Отличие от `list_subtree`: ветка обрывается на первом черновике, поэтому
        снять страницу с публикации значит спрятать и всех её потомков. Сам
        `list_subtree` черновики сохраняет — он обслуживает перемещение,
        удаление и переиндексацию.
        """
        async with self._db.session() as session:
            stmt = self._alive_pages(company_id, namespace).order_by(
                WikiPageRow.depth, WikiPageRow.position, WikiPageRow.title
            )
            rows = list((await session.execute(stmt)).scalars().all())

        by_parent: dict[str | None, list[WikiPageRow]] = {}
        for row in rows:
            by_parent.setdefault(row.parent_page_id, []).append(row)

        root = next((row for row in rows if row.wiki_page_id == root_page_id), None)
        if root is None or not root.is_published:
            return []

        collected: list[WikiPageRow] = [root]
        queue: list[str] = [root_page_id]
        while queue:
            current = queue.pop(0)
            for child in by_parent.get(current, []):
                if not child.is_published:
                    continue
                collected.append(child)
                queue.append(child.wiki_page_id)

        parents_with_published_child = {
            row.parent_page_id for row in collected if row.parent_page_id is not None
        }
        return [
            _row_to_summary(row, row.wiki_page_id in parents_with_published_child)
            for row in collected
        ]

    async def list_ancestors(
        self, company_id: str, namespace: str, wiki_page_id: str
    ) -> list[WikiPage]:
        """Цепочка предков от ближайшего родителя к корню."""
        async with self._db.session() as session:
            stmt = self._alive_pages(company_id, namespace)
            rows = {
                row.wiki_page_id: row
                for row in (await session.execute(stmt)).scalars().all()
            }

        chain: list[WikiPage] = []
        current = rows.get(wiki_page_id)
        seen: set[str] = set()
        while current is not None and current.parent_page_id is not None:
            if current.parent_page_id in seen:
                raise ValueError(f"Цикл в дереве wiki на {current.parent_page_id}")
            seen.add(current.parent_page_id)
            parent = rows.get(current.parent_page_id)
            if parent is None:
                break
            chain.append(_row_to_page(parent))
            current = parent
        return chain

    async def update_page(self, page: WikiPage) -> WikiPage:
        async with self._db.session() as session:
            stmt = select(WikiPageRow).where(
                WikiPageRow.company_id == page.company_id,
                WikiPageRow.namespace == page.namespace,
                WikiPageRow.wiki_page_id == page.wiki_page_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise ValueError(f"Страница {page.wiki_page_id} не найдена в {page.namespace}")

            row.parent_page_id = page.parent_page_id
            row.root_page_id = page.root_page_id
            row.depth = page.depth
            row.position = page.position
            row.title = page.title
            row.icon = page.icon
            row.cover_url = page.cover_url
            row.content = _content_to_json(page.content)
            row.text_markdown = page.text_markdown
            row.company_visible = page.company_visible
            row.is_published = page.is_published
            row.published_at = page.published_at
            row.is_template = page.is_template
            row.is_full_width = page.is_full_width
            row.link_enabled = page.link_enabled
            row.link_permission = page.link_permission.value
            row.last_edited_by_user_id = page.last_edited_by_user_id
            row.revision_count = page.revision_count
            row.updated_at = _utcnow()
            await session.commit()
            await session.refresh(row)
            return _row_to_page(row)

    async def set_link_token(
        self,
        company_id: str,
        namespace: str,
        wiki_page_id: str,
        link_token_hash: str | None,
        link_enabled: bool,
        link_permission: WikiLinkPermission,
    ) -> None:
        async with self._db.session() as session:
            stmt = (
                update(WikiPageRow)
                .where(
                    WikiPageRow.company_id == company_id,
                    WikiPageRow.namespace == namespace,
                    WikiPageRow.wiki_page_id == wiki_page_id,
                )
                .values(
                    link_token_hash=link_token_hash,
                    link_enabled=link_enabled,
                    link_permission=link_permission.value,
                    updated_at=_utcnow(),
                )
            )
            _ = await session.execute(stmt)
            await session.commit()

    async def set_company_visible(
        self, company_id: str, namespace: str, page_ids: list[str], company_visible: bool
    ) -> None:
        if not page_ids:
            return
        async with self._db.session() as session:
            stmt = (
                update(WikiPageRow)
                .where(
                    WikiPageRow.company_id == company_id,
                    WikiPageRow.namespace == namespace,
                    WikiPageRow.wiki_page_id.in_(page_ids),
                )
                .values(company_visible=company_visible)
            )
            _ = await session.execute(stmt)
            await session.commit()

    async def move_subtree_to_namespace(
        self,
        company_id: str,
        source_namespace: str,
        target_namespace: str,
        page_ids: list[str],
        root_page_id: str,
        depth_shift: int,
        new_parent_page_id: str | None,
        moved_page_id: str,
    ) -> None:
        """Перенести поддерево в другой namespace одной транзакцией.

        Частичный перенос недопустим: половина дерева в чужом namespace — это
        и сломанная навигация, и утечка через поиск.
        """
        if not page_ids:
            return
        async with self._db.session() as session:
            stmt = (
                update(WikiPageRow)
                .where(
                    WikiPageRow.company_id == company_id,
                    WikiPageRow.namespace == source_namespace,
                    WikiPageRow.wiki_page_id.in_(page_ids),
                )
                .values(
                    namespace=target_namespace,
                    root_page_id=root_page_id,
                    depth=WikiPageRow.depth + depth_shift,
                    updated_at=_utcnow(),
                )
            )
            _ = await session.execute(stmt)

            _ = await session.execute(
                update(WikiPageRow)
                .where(
                    WikiPageRow.company_id == company_id,
                    WikiPageRow.wiki_page_id == moved_page_id,
                )
                .values(parent_page_id=new_parent_page_id)
            )

            _ = await session.execute(
                update(WikiRevisionRow)
                .where(
                    WikiRevisionRow.company_id == company_id,
                    WikiRevisionRow.namespace == source_namespace,
                    WikiRevisionRow.wiki_page_id.in_(page_ids),
                )
                .values(namespace=target_namespace)
            )
            _ = await session.execute(
                update(WikiPageLinkRow)
                .where(
                    WikiPageLinkRow.company_id == company_id,
                    WikiPageLinkRow.namespace == source_namespace,
                    WikiPageLinkRow.source_page_id.in_(page_ids),
                )
                .values(namespace=target_namespace)
            )
            _ = await session.execute(
                update(WikiCommentRow)
                .where(
                    WikiCommentRow.company_id == company_id,
                    WikiCommentRow.namespace == source_namespace,
                    WikiCommentRow.wiki_page_id.in_(page_ids),
                )
                .values(namespace=target_namespace)
            )
            await session.commit()

    async def reparent_page(
        self,
        company_id: str,
        namespace: str,
        wiki_page_id: str,
        parent_page_id: str | None,
        root_page_id: str,
        position: int,
    ) -> None:
        async with self._db.session() as session:
            stmt = (
                update(WikiPageRow)
                .where(
                    WikiPageRow.company_id == company_id,
                    WikiPageRow.namespace == namespace,
                    WikiPageRow.wiki_page_id == wiki_page_id,
                )
                .values(
                    parent_page_id=parent_page_id,
                    root_page_id=root_page_id,
                    position=position,
                    updated_at=_utcnow(),
                )
            )
            _ = await session.execute(stmt)
            await session.commit()

    async def apply_subtree_depth(
        self,
        company_id: str,
        namespace: str,
        depths: dict[str, int],
        root_page_id: str,
    ) -> None:
        if not depths:
            return
        async with self._db.session() as session:
            for page_id, depth in depths.items():
                _ = await session.execute(
                    update(WikiPageRow)
                    .where(
                        WikiPageRow.company_id == company_id,
                        WikiPageRow.namespace == namespace,
                        WikiPageRow.wiki_page_id == page_id,
                    )
                    .values(depth=depth, root_page_id=root_page_id)
                )
            await session.commit()

    async def soft_delete_pages(
        self, company_id: str, namespace: str, page_ids: list[str]
    ) -> None:
        if not page_ids:
            return
        async with self._db.session() as session:
            stmt = (
                update(WikiPageRow)
                .where(
                    WikiPageRow.company_id == company_id,
                    WikiPageRow.namespace == namespace,
                    WikiPageRow.wiki_page_id.in_(page_ids),
                )
                .values(deleted_at=_utcnow())
            )
            _ = await session.execute(stmt)
            await session.commit()

    async def restore_pages(
        self, company_id: str, namespace: str, page_ids: list[str]
    ) -> None:
        if not page_ids:
            return
        async with self._db.session() as session:
            stmt = (
                update(WikiPageRow)
                .where(
                    WikiPageRow.company_id == company_id,
                    WikiPageRow.namespace == namespace,
                    WikiPageRow.wiki_page_id.in_(page_ids),
                )
                .values(deleted_at=None)
            )
            _ = await session.execute(stmt)
            await session.commit()

    async def list_deleted(self, company_id: str, namespace: str) -> list[WikiPageSummary]:
        async with self._db.session() as session:
            stmt = (
                select(WikiPageRow)
                .where(
                    WikiPageRow.company_id == company_id,
                    WikiPageRow.namespace == namespace,
                    WikiPageRow.deleted_at.is_not(None),
                )
                .order_by(WikiPageRow.deleted_at.desc())
            )
            rows = list((await session.execute(stmt)).scalars().all())
            return [_row_to_summary(row, False) for row in rows]

    async def next_position(
        self, company_id: str, namespace: str, parent_page_id: str | None
    ) -> int:
        async with self._db.session() as session:
            stmt = select(func.coalesce(func.max(WikiPageRow.position), -1)).where(
                WikiPageRow.company_id == company_id,
                WikiPageRow.namespace == namespace,
                WikiPageRow.deleted_at.is_(None),
            )
            if parent_page_id is None:
                stmt = stmt.where(WikiPageRow.parent_page_id.is_(None))
            else:
                stmt = stmt.where(WikiPageRow.parent_page_id == parent_page_id)
            current = (await session.execute(stmt)).scalar_one()
            return int(current) + 1

    # --- полнотекстовый поиск ---

    async def search_pages(
        self,
        company_id: str,
        namespace: str,
        query: str,
        limit: int,
        allowed_page_ids: list[str] | None,
    ) -> list[WikiSearchHit]:
        """Лексический поиск с ранжированием.

        Права применяются здесь же списком разрешённых страниц: возвращать
        строки, а потом фильтровать их в сервисе, значит показывать неверное
        число результатов.
        """
        async with self._db.session() as session:
            tsquery = func.plainto_tsquery("simple", query)
            rank = func.ts_rank(WikiPageRow.search_vector, tsquery)
            stmt = (
                select(WikiPageRow, rank.label("rank"))
                .where(
                    WikiPageRow.company_id == company_id,
                    WikiPageRow.namespace == namespace,
                    WikiPageRow.deleted_at.is_(None),
                    WikiPageRow.search_vector.op("@@")(tsquery),
                )
                .order_by(rank.desc(), WikiPageRow.updated_at.desc())
                .limit(limit)
            )
            if allowed_page_ids is not None:
                stmt = stmt.where(WikiPageRow.wiki_page_id.in_(allowed_page_ids))
            rows: Sequence[tuple[WikiPageRow, float | None]] = (
                (await session.execute(stmt)).tuples().all()
            )

        hits: list[WikiSearchHit] = []
        for row, raw_score in rows:
            score: float = float(raw_score) if raw_score is not None else 0.0
            hits.append(
                WikiSearchHit(
                    wiki_page_id=row.wiki_page_id,
                    namespace=row.namespace,
                    title=row.title,
                    icon=row.icon,
                    snippet=row.text_markdown[:280],
                    score=score,
                    updated_at=row.updated_at,
                )
            )
        return hits

    # --- ревизии ---

    async def insert_revision(self, revision: WikiRevision) -> None:
        async with self._db.session() as session:
            session.add(
                WikiRevisionRow(
                    wiki_revision_id=revision.wiki_revision_id,
                    wiki_page_id=revision.wiki_page_id,
                    company_id=revision.company_id,
                    namespace=revision.namespace,
                    title=revision.title,
                    content=_content_to_json(revision.content),
                    text_markdown=revision.text_markdown,
                    author_user_id=revision.author_user_id,
                    created_at=revision.created_at,
                )
            )
            await session.commit()

    async def list_revisions(
        self, company_id: str, namespace: str, wiki_page_id: str, limit: int
    ) -> list[WikiRevisionSummary]:
        async with self._db.session() as session:
            stmt = (
                select(
                    WikiRevisionRow.wiki_revision_id,
                    WikiRevisionRow.wiki_page_id,
                    WikiRevisionRow.title,
                    WikiRevisionRow.author_user_id,
                    WikiRevisionRow.created_at,
                )
                .where(
                    WikiRevisionRow.company_id == company_id,
                    WikiRevisionRow.namespace == namespace,
                    WikiRevisionRow.wiki_page_id == wiki_page_id,
                )
                .order_by(WikiRevisionRow.created_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).tuples().all()
            return [
                WikiRevisionSummary(
                    wiki_revision_id=revision_id,
                    wiki_page_id=page_id,
                    title=title,
                    author_user_id=author,
                    created_at=created_at,
                )
                for revision_id, page_id, title, author, created_at in rows
            ]

    async def get_revision(
        self, company_id: str, namespace: str, wiki_revision_id: str
    ) -> WikiRevision | None:
        async with self._db.session() as session:
            stmt = select(WikiRevisionRow).where(
                WikiRevisionRow.company_id == company_id,
                WikiRevisionRow.namespace == namespace,
                WikiRevisionRow.wiki_revision_id == wiki_revision_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _row_to_revision(row) if row is not None else None

    # --- ссылки и backlinks ---

    async def replace_page_links(
        self, company_id: str, namespace: str, source_page_id: str, links: list[WikiPageLink]
    ) -> None:
        """Переписать исходящие ссылки страницы.

        Полная замена, а не досыпание: удалённое из текста упоминание обязано
        исчезнуть и из обратных ссылок на карточке сущности.
        """
        async with self._db.session() as session:
            _ = await session.execute(
                delete(WikiPageLinkRow).where(
                    WikiPageLinkRow.company_id == company_id,
                    WikiPageLinkRow.namespace == namespace,
                    WikiPageLinkRow.source_page_id == source_page_id,
                )
            )
            for link in links:
                session.add(
                    WikiPageLinkRow(
                        wiki_page_link_id=link.wiki_page_link_id,
                        company_id=link.company_id,
                        namespace=link.namespace,
                        source_page_id=link.source_page_id,
                        target_kind=link.target_kind.value,
                        target_id=link.target_id,
                        target_label=link.target_label,
                        created_at=link.created_at,
                    )
                )
            await session.commit()

    async def list_page_links(
        self, company_id: str, namespace: str, source_page_id: str
    ) -> list[WikiPageLink]:
        async with self._db.session() as session:
            stmt = select(WikiPageLinkRow).where(
                WikiPageLinkRow.company_id == company_id,
                WikiPageLinkRow.namespace == namespace,
                WikiPageLinkRow.source_page_id == source_page_id,
            )
            rows = list((await session.execute(stmt)).scalars().all())
            return [_row_to_link(row) for row in rows]

    async def list_backlinks(
        self,
        company_id: str,
        target_kind: WikiLinkTargetKind,
        target_id: str,
        limit: int,
    ) -> list[WikiBacklink]:
        """Кто ссылается на цель.

        Namespace здесь не фильтр, а результат: карточка сущности Networkle
        показывает связи из всех пространств компании, доступных пользователю,
        и отсев по правам делает сервис.
        """
        async with self._db.session() as session:
            stmt = (
                select(WikiPageLinkRow, WikiPageRow)
                .join(
                    WikiPageRow,
                    WikiPageRow.wiki_page_id == WikiPageLinkRow.source_page_id,
                )
                .where(
                    WikiPageLinkRow.company_id == company_id,
                    WikiPageLinkRow.target_kind == target_kind.value,
                    WikiPageLinkRow.target_id == target_id,
                    WikiPageRow.deleted_at.is_(None),
                )
                .order_by(WikiPageRow.updated_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).tuples().all()

        return [
            WikiBacklink(
                wiki_page_id=page.wiki_page_id,
                namespace=page.namespace,
                title=page.title,
                icon=page.icon,
                target_kind=WikiLinkTargetKind(link.target_kind),
                target_id=link.target_id,
                updated_at=page.updated_at,
            )
            for link, page in rows
        ]

    # --- комментарии ---

    async def insert_comment(self, comment: WikiComment) -> WikiComment:
        async with self._db.session() as session:
            row = WikiCommentRow(
                wiki_comment_id=comment.wiki_comment_id,
                wiki_page_id=comment.wiki_page_id,
                company_id=comment.company_id,
                namespace=comment.namespace,
                parent_comment_id=comment.parent_comment_id,
                author_user_id=comment.author_user_id,
                body_markdown=comment.body_markdown,
                anchor_text=comment.anchor_text,
                created_at=comment.created_at,
                updated_at=comment.updated_at,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _row_to_comment(row)

    async def list_comments(
        self, company_id: str, namespace: str, wiki_page_id: str
    ) -> list[WikiComment]:
        async with self._db.session() as session:
            stmt = (
                select(WikiCommentRow)
                .where(
                    WikiCommentRow.company_id == company_id,
                    WikiCommentRow.namespace == namespace,
                    WikiCommentRow.wiki_page_id == wiki_page_id,
                )
                .order_by(WikiCommentRow.created_at)
            )
            rows = list((await session.execute(stmt)).scalars().all())
            return [_row_to_comment(row) for row in rows]

    async def resolve_comment(
        self,
        company_id: str,
        namespace: str,
        wiki_comment_id: str,
        resolved_by_user_id: str | None,
    ) -> WikiComment | None:
        async with self._db.session() as session:
            stmt = select(WikiCommentRow).where(
                WikiCommentRow.company_id == company_id,
                WikiCommentRow.namespace == namespace,
                WikiCommentRow.wiki_comment_id == wiki_comment_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            row.resolved_at = _utcnow() if resolved_by_user_id is not None else None
            row.resolved_by_user_id = resolved_by_user_id
            await session.commit()
            await session.refresh(row)
            return _row_to_comment(row)

    async def delete_comment(
        self, company_id: str, namespace: str, wiki_comment_id: str
    ) -> None:
        async with self._db.session() as session:
            stmt = delete(WikiCommentRow).where(
                WikiCommentRow.company_id == company_id,
                WikiCommentRow.namespace == namespace,
                WikiCommentRow.wiki_comment_id == wiki_comment_id,
            )
            _ = await session.execute(stmt)
            await session.commit()


__all__ = ["WikiRepository"]
