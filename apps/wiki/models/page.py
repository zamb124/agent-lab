"""Таблица wiki."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import F, Index, atomic, execute_raw
from oxyde import Field as DbField

from apps.wiki.content.prosemirror import ProseMirrorNode
from apps.wiki.models.comment import WikiComment
from apps.wiki.models.domain import (
    WikiLinkPermission,
    WikiPageSummary,
    WikiSearchHit,
    WikiVisibility,
)
from apps.wiki.models.page_link import WikiPageLink
from apps.wiki.models.revision import WikiRevision
from core.auth.utils import hash_token
from core.models.platform_model import PlatformModel
from core.types import JsonValue, parse_json_object, require_json_object
from core.utils.time import utcnow


class WikiPage(PlatformModel):
    """Страница wiki. Таблица ``wiki_pages``.

    `content` — источник правды. `text_markdown` производный: его пишет только
    `WikiService`. `search_vector` — generated-колонка и полем модели не является:
    UPDATE её не пишет, Postgres пересчитывает её из `title` и `text_markdown`.
    `company_visible` — материализация FGA `company_viewer`.
    """

    __database_alias__: ClassVar[str | None] = "wiki"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "wiki_pages"
        indexes: list[Index] = [
            Index(["company_id", "namespace", "parent_page_id", "position"]),
            Index(["company_id", "namespace", "root_page_id"]),
            Index(["company_id", "namespace", "updated_at"]),
        ]

    wiki_page_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    namespace: str = DbField(max_length=100)
    root_page_id: str = DbField(max_length=64)
    content: ProseMirrorNode = DbField(db_type="JSONB")
    created_by_user_id: str = DbField(max_length=100)
    last_edited_by_user_id: str = DbField(max_length=100)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    parent_page_id: str | None = DbField(default=None, max_length=64)
    depth: int = DbField(default=0, ge=0)
    position: int = DbField(default=0)
    title: str = DbField(default="", db_type="TEXT")
    icon: str = DbField(default="", max_length=64)
    cover_url: str = DbField(default="", db_type="TEXT")
    text_markdown: str = DbField(default="", db_type="TEXT")
    company_visible: bool = DbField(default=True)
    is_published: bool = DbField(default=True)
    published_at: datetime | None = DbField(default=None)
    is_template: bool = DbField(default=False)
    is_full_width: bool = DbField(default=False)
    link_enabled: bool = DbField(default=False)
    link_token_hash: str | None = DbField(default=None, max_length=128, db_index=True)
    link_permission: WikiLinkPermission = DbField(default=WikiLinkPermission.VIEWER)
    revision_count: int = DbField(default=0, ge=0)
    deleted_at: datetime | None = DbField(default=None)

    @classmethod
    async def list_deleted_by_deleted_at_desc(cls, company_id: str, namespace: str) -> list[Self]:
        """Удалённые страницы namespace, ORDER BY deleted_at DESC. Предела нет. Пустые поля не проверяются."""
        return await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            deleted_at__isnull=False,
        ).order_by("-deleted_at").all()

    @classmethod
    async def find_published_link(cls, raw_token: str) -> Self | None:
        """Корень публичного сайта — страница, на которой включена ссылка.

        Черновик по ссылке не отдаётся: включённая ссылка — намерение поделиться
        готовым текстом, а `is_published=False` говорит обратное.
        """
        return await cls.objects.filter(
            link_token_hash=hash_token(raw_token),
            link_enabled=True,
            is_published=True,
            deleted_at=None,
        ).get_or_none()

    @classmethod
    async def create(cls, page: Self) -> Self:
        return await cls.objects.create(instance=page)

    @classmethod
    async def delete_in_namespace(
        cls,
        company_id: str,
        namespace: str,
        wiki_page_id: str,
    ) -> int:
        return await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            wiki_page_id=wiki_page_id,
        ).delete()

    @classmethod
    async def update_location(
        cls,
        *,
        company_id: str,
        namespace: str,
        wiki_page_id: str,
        parent_page_id: str | None,
        root_page_id: str,
        position: int,
        updated_at: datetime,
    ) -> None:
        _ = await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            wiki_page_id=wiki_page_id,
        ).update(
            using="wiki",
            parent_page_id=parent_page_id,
            root_page_id=root_page_id,
            position=position,
            updated_at=updated_at,
        )

    @classmethod
    async def mark_deleted(
        cls,
        *,
        company_id: str,
        namespace: str,
        wiki_page_ids: list[str],
        deleted_at: datetime,
    ) -> None:
        _ = await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            wiki_page_id__in=wiki_page_ids,
        ).update(using="wiki", deleted_at=deleted_at)

    @classmethod
    async def update_deleted_at(
        cls,
        *,
        company_id: str,
        namespace: str,
        wiki_page_id: str,
        deleted_at: datetime | None,
    ) -> None:
        _ = await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            wiki_page_id=wiki_page_id,
        ).update(using="wiki", deleted_at=deleted_at)

    @classmethod
    async def update_depth_and_root(
        cls,
        *,
        company_id: str,
        namespace: str,
        wiki_page_id: str,
        depth: int,
        root_page_id: str,
    ) -> None:
        _ = await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            wiki_page_id=wiki_page_id,
        ).update(using="wiki", depth=depth, root_page_id=root_page_id)

    @classmethod
    async def alive_by_created_at_asc(cls, *, limit: int | None) -> list[Self]:
        """Живые страницы, ORDER BY created_at ASC. limit is None не ограничивает. limit < 1 — ValueError."""
        query = cls.objects.filter(deleted_at=None).order_by("created_at")
        if limit is not None:
            if limit < 1:
                raise ValueError("limit must be >= 1")
            query = query.limit(limit)
        return await query.all()

    @classmethod
    async def apply_depths(
        cls,
        *,
        company_id: str,
        namespace: str,
        depths: dict[str, int],
        root_page_id: str,
    ) -> None:
        if len(depths) == 0:
            return
        async with atomic(using="wiki"):
            for wiki_page_id, depth in depths.items():
                await cls.update_depth_and_root(
                    company_id=company_id,
                    namespace=namespace,
                    wiki_page_id=wiki_page_id,
                    depth=depth,
                    root_page_id=root_page_id,
                )

    @classmethod
    async def alive_page_in_company(
        cls,
        company_id: str,
        wiki_page_id: str,
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id,
            wiki_page_id=wiki_page_id,
            deleted_at=None,
        ).get_or_none()

    @classmethod
    async def list_alive_by_title_asc(
        cls,
        company_id: str,
        query: str,
        limit: int,
    ) -> list[Self]:
        """Живые страницы компании по возрастанию title, не больше limit. Пустой query не фильтрует заголовок."""
        rows = cls.objects.filter(company_id=company_id, deleted_at=None)
        if query != "":
            rows = rows.filter(title__icontains=query)
        return await rows.order_by("title").limit(limit).all()

    @classmethod
    async def alive_page(
        cls,
        company_id: str,
        namespace: str,
        wiki_page_id: str,
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            wiki_page_id=wiki_page_id,
            deleted_at=None,
        ).get_or_none()

    @classmethod
    async def update_in_namespace(cls, page: Self) -> Self:
        existing = await cls.objects.filter(
            company_id=page.company_id,
            namespace=page.namespace,
            wiki_page_id=page.wiki_page_id,
        ).get_or_none()
        if existing is None:
            raise ValueError(f"Page {page.wiki_page_id} not found in {page.namespace}")
        page.updated_at = utcnow()
        _ = await page.save()
        return page

    @classmethod
    async def update_link(
        cls,
        company_id: str,
        namespace: str,
        wiki_page_id: str,
        link_token_hash: str | None,
        link_enabled: bool,
        link_permission: WikiLinkPermission,
    ) -> None:
        _ = await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            wiki_page_id=wiki_page_id,
        ).update(
            using="wiki",
            link_token_hash=link_token_hash,
            link_enabled=link_enabled,
            link_permission=link_permission,
            updated_at=utcnow(),
        )

    @classmethod
    async def update_company_visible(
        cls,
        company_id: str,
        namespace: str,
        page_ids: list[str],
        company_visible: bool,
    ) -> None:
        _ = await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            wiki_page_id__in=page_ids,
        ).update(using="wiki", company_visible=company_visible)

    @classmethod
    async def list_unordered_alive(cls, company_id: str, wiki_page_ids: list[str]) -> list[Self]:
        """Живые страницы из списка id. deleted_at пустой. Пустой список id — []. Порядка и limit нет."""
        if len(wiki_page_ids) == 0:
            return []
        return await cls.objects.filter(
            company_id=company_id,
            wiki_page_id__in=wiki_page_ids,
            deleted_at=None,
        ).all()

    @classmethod
    def _alive(cls, company_id: str, namespace: str):
        return cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            deleted_at=None,
        )

    @staticmethod
    def _summary(page: WikiPage, has_children: bool) -> WikiPageSummary:
        return WikiPageSummary(
            wiki_page_id=page.wiki_page_id,
            namespace=page.namespace,
            parent_page_id=page.parent_page_id,
            root_page_id=page.root_page_id,
            depth=page.depth,
            position=page.position,
            title=page.title,
            icon=page.icon,
            company_visible=page.company_visible,
            is_published=page.is_published,
            is_template=page.is_template,
            has_children=has_children,
            updated_at=page.updated_at,
            last_edited_by_user_id=page.last_edited_by_user_id,
        )

    @staticmethod
    def _search_hit(row: JsonValue) -> WikiSearchHit:
        parsed = require_json_object(row, "wiki_search")
        raw_page = parsed["page"]
        if isinstance(raw_page, str):
            payload = parse_json_object(raw_page, "wiki_page")
        else:
            payload = require_json_object(raw_page, "wiki_page")
        page = WikiPage.model_validate(payload)
        raw_rank = parsed["search_rank"]
        if isinstance(raw_rank, str):
            raw_rank = float(raw_rank)
        if isinstance(raw_rank, bool) or not isinstance(raw_rank, (int, float)):
            raise TypeError("wiki search rank must be a number")
        return WikiSearchHit(
            wiki_page_id=page.wiki_page_id,
            namespace=page.namespace,
            title=page.title,
            icon=page.icon,
            snippet=page.text_markdown[:280],
            score=float(raw_rank),
            updated_at=page.updated_at,
        )

    @classmethod
    async def list_alive_summaries_by_depth_position_and_title_asc(cls, company_id: str, namespace: str) -> list[WikiPageSummary]:
        """Сводки живых страниц namespace, ORDER BY depth, position, title ASC. Предела нет. У страницы с детьми has_children. Пустые поля не проверяются."""
        pages = await cls._alive(company_id, namespace).order_by("depth", "position", "title").all()
        parents = {page.parent_page_id for page in pages if page.parent_page_id is not None}
        return [cls._summary(page, page.wiki_page_id in parents) for page in pages]

    @classmethod
    async def list_unordered_subtree(
        cls, company_id: str, namespace: str, wiki_page_id: str
    ) -> list[Self]:
        """Страница и потомки. Живые страницы namespace читаются без порядка. Обход стеком. Нет страницы — []."""
        pages = await cls._alive(company_id, namespace).all()
        by_parent: dict[str | None, list[Self]] = {}
        for page in pages:
            by_parent.setdefault(page.parent_page_id, []).append(page)
        root = next((page for page in pages if page.wiki_page_id == wiki_page_id), None)
        if root is None:
            return []
        collected: list[Self] = [root]
        queue: list[str] = [wiki_page_id]
        while len(queue) > 0:
            current = queue.pop()
            for child in by_parent.get(current, []):
                collected.append(child)
                queue.append(child.wiki_page_id)
        return collected

    @classmethod
    async def list_published_subtree_summaries_breadth_first(
        cls, company_id: str, namespace: str, root_page_id: str
    ) -> list[WikiPageSummary]:
        """Сводки опубликованной ветки, обход в ширину. Дети внутри родителя идут как depth, position, title. Неопубликованный узел обрывает ветку. Нет корня или корень не опубликован — []."""
        pages = await cls._alive(company_id, namespace).order_by("depth", "position", "title").all()
        by_parent: dict[str | None, list[Self]] = {}
        for page in pages:
            by_parent.setdefault(page.parent_page_id, []).append(page)
        root = next((page for page in pages if page.wiki_page_id == root_page_id), None)
        if root is None or not root.is_published:
            return []
        collected: list[Self] = [root]
        queue: list[str] = [root_page_id]
        while len(queue) > 0:
            current = queue.pop(0)
            for child in by_parent.get(current, []):
                if not child.is_published:
                    continue
                collected.append(child)
                queue.append(child.wiki_page_id)
        parents_with_published_child = {
            page.parent_page_id for page in collected if page.parent_page_id is not None
        }
        return [
            cls._summary(page, page.wiki_page_id in parents_with_published_child)
            for page in collected
        ]

    @classmethod
    async def ancestors_toward_root(
        cls, company_id: str, namespace: str, wiki_page_id: str
    ) -> list[Self]:
        """Цепочка предков от ближайшего родителя к корню."""
        pages = {page.wiki_page_id: page for page in await cls._alive(company_id, namespace).all()}
        chain: list[Self] = []
        current = pages.get(wiki_page_id)
        seen: set[str] = set()
        while current is not None and current.parent_page_id is not None:
            if current.parent_page_id in seen:
                raise ValueError(f"Cycle in wiki tree at {current.parent_page_id}")
            seen.add(current.parent_page_id)
            parent = pages.get(current.parent_page_id)
            if parent is None:
                break
            chain.append(parent)
            current = parent
        return chain

    @classmethod
    async def move_subtree_bundle_to_namespace(
        cls,
        company_id: str,
        source_namespace: str,
        target_namespace: str,
        page_ids: list[str],
        root_page_id: str,
        depth_shift: int,
        new_parent_page_id: str | None,
        moved_page_id: str,
    ) -> None:
        """Перенести поддерево в другой namespace одной транзакцией."""
        if len(page_ids) == 0:
            return
        async with atomic(using="wiki"):
            _ = await cls.objects.filter(
                company_id=company_id,
                namespace=source_namespace,
                wiki_page_id__in=page_ids,
            ).update(
                using="wiki",
                namespace=target_namespace,
                root_page_id=root_page_id,
                depth=F("depth") + depth_shift,
                updated_at=utcnow(),
            )
            _ = await cls.objects.filter(
                company_id=company_id,
                wiki_page_id=moved_page_id,
            ).update(using="wiki", parent_page_id=new_parent_page_id)
            _ = await WikiRevision.objects.filter(
                company_id=company_id,
                namespace=source_namespace,
                wiki_page_id__in=page_ids,
            ).update(using="wiki", namespace=target_namespace)
            _ = await WikiPageLink.objects.filter(
                company_id=company_id,
                namespace=source_namespace,
                source_page_id__in=page_ids,
            ).update(using="wiki", namespace=target_namespace)
            _ = await WikiComment.objects.filter(
                company_id=company_id,
                namespace=source_namespace,
                wiki_page_id__in=page_ids,
            ).update(using="wiki", namespace=target_namespace)

    @classmethod
    async def next_position(
        cls, company_id: str, namespace: str, parent_page_id: str | None
    ) -> int:
        params: list[str] = [company_id, namespace]
        parent_sql = "parent_page_id IS NULL"
        if parent_page_id is not None:
            params.append(parent_page_id)
            parent_sql = f"parent_page_id = ${len(params)}"
        rows = await execute_raw(
            "SELECT COALESCE(MAX(position), -1)::int AS max_position "
            + "FROM wiki_pages "
            + f"WHERE company_id = $1 AND namespace = $2 AND deleted_at IS NULL AND {parent_sql}",
            params,
            using="wiki",
        )
        max_position = require_json_object(rows[0], "wiki_position")["max_position"]
        if isinstance(max_position, bool) or not isinstance(max_position, int):
            raise TypeError("wiki position must be int")
        return max_position + 1

    @classmethod
    async def list_alive_search_hits_by_rank_desc_and_updated_at_desc(
        cls,
        company_id: str,
        namespace: str,
        query: str,
        limit: int,
        allowed_page_ids: list[str] | None,
    ) -> list[WikiSearchHit]:
        """Живые страницы namespace по search_vector как WikiSearchHit. Ранг DESC, затем updated_at DESC. Не больше limit. Пустой allowed_page_ids — []."""
        if allowed_page_ids is not None and len(allowed_page_ids) == 0:
            return []
        params: list[str | int] = [query, company_id, namespace, limit]
        allowed_sql = ""
        if allowed_page_ids is not None:
            placeholders: list[str] = []
            for page_id in allowed_page_ids:
                params.append(page_id)
                placeholders.append(f"${len(params)}")
            allowed_sql = f" AND wiki_page_id IN ({', '.join(placeholders)})"
        rows = await execute_raw(
            "SELECT row_to_json(wiki_pages) AS page, "
            + "ts_rank(search_vector, plainto_tsquery('simple', $1))::text AS search_rank "
            + "FROM wiki_pages "
            + "WHERE company_id = $2 AND namespace = $3 AND deleted_at IS NULL "
            + "AND search_vector @@ plainto_tsquery('simple', $1)"
            + allowed_sql
            + " ORDER BY ts_rank(search_vector, plainto_tsquery('simple', $1)) DESC, "
            + "updated_at DESC LIMIT $4",
            params,
            using="wiki",
        )
        return [cls._search_hit(row) for row in rows]

    @property
    def rag_visibility(self) -> WikiVisibility:
        if self.company_visible:
            return WikiVisibility.COMPANY
        return WikiVisibility.RESTRICTED
