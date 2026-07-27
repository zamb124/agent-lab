"""
Бизнес-логика wiki.

Единственная точка записи страницы. Здесь и только здесь:

* из `content` выводится `text_markdown` — снаружи это поле не пишется;
* пересчитывается видимость поддерева и переносится индекс RAG;
* переписываются исходящие ссылки и публикуются доменные события.

Namespace передаётся во все методы явно и уходит в каждый запрос репозитория:
операции «по одному id» без пространства не существует.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from apps.wiki.content.markdown_serializer import document_to_markdown
from apps.wiki.content.prosemirror import ProseMirrorNode, empty_document
from apps.wiki.content.schema import normalize_document
from apps.wiki.db.repositories.wiki_repository import WikiRepository
from apps.wiki.events import (
    WIKI_COMMENT_CREATED,
    WIKI_COMMENT_RESOLVED,
    WIKI_PAGE_CREATED,
    WIKI_PAGE_RESTORED,
    WIKI_PAGE_UPDATED,
    publish_wiki_access_changed,
    publish_wiki_comment_event,
    publish_wiki_page_deleted,
    publish_wiki_page_event,
    publish_wiki_page_moved,
)
from apps.wiki.models.domain import (
    WikiBacklink,
    WikiComment,
    WikiLinkPermission,
    WikiLinkTargetKind,
    WikiPage,
    WikiPageAccess,
    WikiPageLink,
    WikiPageMember,
    WikiPagePermission,
    WikiPageSummary,
    WikiRevision,
    WikiRevisionSummary,
    WikiSearchHit,
    WikiVisibility,
)
from apps.wiki.services.access import WikiAccessResolver
from apps.wiki.services.links import ExtractedMention, extract_links, extract_user_mentions
from apps.wiki.services.rag_index import WikiRagIndexService
from apps.wiki.services.rag_metadata import (
    WikiRagFilterOverflowError,
    WikiSearchFilter,
    build_wiki_search_filter,
    ensure_page_filter_size,
)
from core.logging import get_logger
from core.rag.models import RAGMetadataFilter

logger = get_logger(__name__)


class WikiPageNotFoundError(LookupError):
    """Страницы нет в этом пространстве.

    Отдельный тип нужен, чтобы HTTP-слой всегда отвечал 404 — и для
    несуществующей страницы, и для страницы чужого namespace: разное поведение
    выдавало бы факт её существования.
    """


class WikiAccessDeniedError(PermissionError):
    """Пользователю нельзя выполнить операцию над страницей."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def _hash_link_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


class WikiService:
    """Операции над страницами и их окружением."""

    def __init__(self, repository: WikiRepository, rag_index: WikiRagIndexService) -> None:
        self._repo: WikiRepository = repository
        self._rag: WikiRagIndexService = rag_index

    # --- доступ ---

    async def build_access_resolver(
        self, company_id: str, namespace: str, user_id: str | None
    ) -> WikiAccessResolver:
        tree = await self._repo.list_tree(company_id, namespace)
        parents = {item.wiki_page_id: item.parent_page_id for item in tree}
        restricted = await self._repo.list_restricted_page_ids(company_id, namespace)

        user_permissions: dict[str, WikiPagePermission] = {}
        if user_id is not None:
            member_pages = await self._repo.list_members_for_pages(
                company_id, namespace, list(restricted)
            )
            for page_id, members in member_pages.items():
                for member in members:
                    if member.user_id == user_id:
                        user_permissions[page_id] = member.permission

        page_owners = await self._page_owners(company_id, namespace)
        return WikiAccessResolver(
            parents=parents,
            restricted_page_ids=restricted,
            user_permissions=user_permissions,
            page_owners=page_owners,
            user_id=user_id,
        )

    async def _page_owners(self, company_id: str, namespace: str) -> dict[str, str]:
        pages = await self._repo.list_tree(company_id, namespace)
        return {item.wiki_page_id: item.last_edited_by_user_id for item in pages}

    async def require_page(
        self, company_id: str, namespace: str, wiki_page_id: str
    ) -> WikiPage:
        page = await self._repo.get_page(company_id, namespace, wiki_page_id)
        if page is None:
            raise WikiPageNotFoundError(f"Страница {wiki_page_id} не найдена в {namespace}")
        return page

    async def require_viewable_page(
        self, company_id: str, namespace: str, wiki_page_id: str, user_id: str
    ) -> WikiPage:
        page = await self.require_page(company_id, namespace, wiki_page_id)
        resolver = await self.build_access_resolver(company_id, namespace, user_id)
        if not resolver.can_view(wiki_page_id):
            raise WikiAccessDeniedError(f"Нет доступа к странице {wiki_page_id}")
        return page

    async def require_editable_page(
        self, company_id: str, namespace: str, wiki_page_id: str, user_id: str
    ) -> WikiPage:
        page = await self.require_page(company_id, namespace, wiki_page_id)
        resolver = await self.build_access_resolver(company_id, namespace, user_id)
        if not resolver.can_edit(wiki_page_id):
            raise WikiAccessDeniedError(f"Нет прав на изменение страницы {wiki_page_id}")
        return page

    # --- чтение ---

    async def list_tree(
        self, company_id: str, namespace: str, user_id: str
    ) -> list[WikiPageSummary]:
        tree = await self._repo.list_tree(company_id, namespace)
        resolver = await self.build_access_resolver(company_id, namespace, user_id)
        return [item for item in tree if resolver.can_view(item.wiki_page_id)]

    async def list_deleted(
        self, company_id: str, namespace: str, user_id: str
    ) -> list[WikiPageSummary]:
        deleted = await self._repo.list_deleted(company_id, namespace)
        resolver = await self.build_access_resolver(company_id, namespace, user_id)
        return [item for item in deleted if resolver.can_view(item.wiki_page_id)]

    async def get_page_by_link_token(self, raw_token: str) -> WikiPage | None:
        return await self._repo.get_page_by_link_token(_hash_link_token(raw_token))

    # --- запись ---

    async def create_page(
        self,
        company_id: str,
        namespace: str,
        user_id: str,
        title: str,
        parent_page_id: str | None,
        content: ProseMirrorNode | None,
        icon: str = "",
    ) -> WikiPage:
        parent: WikiPage | None = None
        if parent_page_id is not None:
            parent = await self.require_editable_page(
                company_id, namespace, parent_page_id, user_id
            )

        document = normalize_document(content) if content is not None else empty_document()
        now = _utcnow()
        wiki_page_id = _new_id("wpg")
        position = await self._repo.next_position(company_id, namespace, parent_page_id)

        page = WikiPage(
            wiki_page_id=wiki_page_id,
            company_id=company_id,
            namespace=namespace,
            parent_page_id=parent_page_id,
            root_page_id=parent.root_page_id if parent is not None else wiki_page_id,
            depth=parent.depth + 1 if parent is not None else 0,
            position=position,
            title=title,
            icon=icon,
            content=document,
            text_markdown=document_to_markdown(document),
            visibility=WikiVisibility.COMPANY,
            created_by_user_id=user_id,
            last_edited_by_user_id=user_id,
            published_at=now,
            created_at=now,
            updated_at=now,
        )

        resolver = await self.build_access_resolver(company_id, namespace, user_id)
        if parent_page_id is not None:
            page.visibility = resolver.visibility(parent_page_id)

        stored = await self._repo.insert_page(page)
        await self._sync_links(stored)
        await self._rag.index_page(stored)
        await publish_wiki_page_event(
            WIKI_PAGE_CREATED, self._to_summary(stored, False), company_id
        )
        return stored

    async def update_page_content(
        self,
        company_id: str,
        namespace: str,
        user_id: str,
        wiki_page_id: str,
        content: ProseMirrorNode,
        title: str | None = None,
        create_revision: bool = True,
    ) -> WikiPage:
        """Записать новое содержимое страницы.

        Прошлая версия уходит в ревизию до перезаписи, иначе восстанавливать
        будет нечего.
        """
        page = await self.require_editable_page(company_id, namespace, wiki_page_id, user_id)

        if create_revision:
            await self._store_revision(page)

        document = normalize_document(content)
        page.content = document
        page.text_markdown = document_to_markdown(document)
        page.last_edited_by_user_id = user_id
        page.revision_count = page.revision_count + 1 if create_revision else page.revision_count
        if title is not None:
            page.title = title

        stored = await self._repo.update_page(page)
        await self._sync_links(stored)
        await self._rag.index_page(stored)
        await publish_wiki_page_event(
            WIKI_PAGE_UPDATED, self._to_summary(stored, False), company_id
        )
        return stored

    async def update_page_properties(
        self,
        company_id: str,
        namespace: str,
        user_id: str,
        wiki_page_id: str,
        title: str | None = None,
        icon: str | None = None,
        cover_url: str | None = None,
        is_published: bool | None = None,
        is_template: bool | None = None,
    ) -> WikiPage:
        page = await self.require_editable_page(company_id, namespace, wiki_page_id, user_id)

        if title is not None:
            page.title = title
        if icon is not None:
            page.icon = icon
        if cover_url is not None:
            page.cover_url = cover_url
        if is_published is not None:
            page.is_published = is_published
            if is_published and page.published_at is None:
                page.published_at = _utcnow()
        if is_template is not None:
            page.is_template = is_template
        page.last_edited_by_user_id = user_id

        stored = await self._repo.update_page(page)
        await self._rag.index_page(stored)
        await publish_wiki_page_event(
            WIKI_PAGE_UPDATED, self._to_summary(stored, False), company_id
        )
        return stored

    async def move_page(
        self,
        company_id: str,
        namespace: str,
        user_id: str,
        wiki_page_id: str,
        new_parent_page_id: str | None,
        position: int | None = None,
    ) -> WikiPage:
        """Перенести страницу внутри пространства."""
        page = await self.require_editable_page(company_id, namespace, wiki_page_id, user_id)
        subtree = await self._repo.list_subtree(company_id, namespace, wiki_page_id)
        subtree_ids = {item.wiki_page_id for item in subtree}

        if new_parent_page_id is not None:
            if new_parent_page_id in subtree_ids:
                raise ValueError("Нельзя перенести страницу внутрь её собственного поддерева")
            parent = await self.require_editable_page(
                company_id, namespace, new_parent_page_id, user_id
            )
            new_root = parent.root_page_id
            new_depth = parent.depth + 1
        else:
            parent = None
            new_root = wiki_page_id
            new_depth = 0

        previous_parent = page.parent_page_id
        target_position = (
            position
            if position is not None
            else await self._repo.next_position(company_id, namespace, new_parent_page_id)
        )

        await self._repo.reparent_page(
            company_id, namespace, wiki_page_id, new_parent_page_id, new_root, target_position
        )
        await self._apply_depths(company_id, namespace, subtree, wiki_page_id, new_depth, new_root)
        await self._recalculate_visibility(company_id, namespace, wiki_page_id)

        stored = await self.require_page(company_id, namespace, wiki_page_id)
        await publish_wiki_page_moved(
            self._to_summary(stored, bool(subtree_ids - {wiki_page_id})),
            company_id,
            previous_namespace=namespace,
            previous_parent_page_id=previous_parent,
        )
        return stored

    async def move_page_to_namespace(
        self,
        company_id: str,
        namespace: str,
        target_namespace: str,
        user_id: str,
        wiki_page_id: str,
        new_parent_page_id: str | None,
    ) -> WikiPage:
        """Перенести страницу и всё поддерево в другое пространство.

        Отдельная операция, а не поле в `PATCH`: перенос меняет границу
        изоляции, поэтому он всегда явный и всегда затрагивает поддерево
        целиком.
        """
        if target_namespace == namespace:
            raise ValueError("Целевое пространство совпадает с текущим")

        page = await self.require_editable_page(company_id, namespace, wiki_page_id, user_id)
        subtree = await self._repo.list_subtree(company_id, namespace, wiki_page_id)
        subtree_ids = [item.wiki_page_id for item in subtree]

        target_parent: WikiPage | None = None
        if new_parent_page_id is not None:
            target_parent = await self.require_editable_page(
                company_id, target_namespace, new_parent_page_id, user_id
            )

        new_depth = target_parent.depth + 1 if target_parent is not None else 0
        new_root = target_parent.root_page_id if target_parent is not None else wiki_page_id

        for item in subtree:
            await self._rag.remove_page(item)

        await self._repo.move_subtree_to_namespace(
            company_id=company_id,
            source_namespace=namespace,
            target_namespace=target_namespace,
            page_ids=subtree_ids,
            root_page_id=new_root,
            depth_shift=new_depth - page.depth,
            new_parent_page_id=new_parent_page_id,
            moved_page_id=wiki_page_id,
        )

        moved_subtree = await self._repo.list_subtree(
            company_id, target_namespace, wiki_page_id
        )
        await self._recalculate_visibility(company_id, target_namespace, wiki_page_id)
        refreshed = await self._repo.list_subtree(company_id, target_namespace, wiki_page_id)
        await self._rag.reindex_subtree(refreshed)

        stored = await self.require_page(company_id, target_namespace, wiki_page_id)
        await publish_wiki_page_moved(
            self._to_summary(stored, len(moved_subtree) > 1),
            company_id,
            previous_namespace=namespace,
            previous_parent_page_id=page.parent_page_id,
        )
        logger.info(
            "wiki.page.namespace_changed",
            extra={
                "wiki_page_id": wiki_page_id,
                "source_namespace": namespace,
                "target_namespace": target_namespace,
                "pages": len(subtree_ids),
            },
        )
        return stored

    async def delete_page(
        self, company_id: str, namespace: str, user_id: str, wiki_page_id: str
    ) -> list[str]:
        """Мягко удалить страницу вместе с поддеревом."""
        resolver = await self.build_access_resolver(company_id, namespace, user_id)
        _ = await self.require_page(company_id, namespace, wiki_page_id)
        if not resolver.can_administer(wiki_page_id):
            raise WikiAccessDeniedError(f"Нет прав на удаление страницы {wiki_page_id}")

        subtree = await self._repo.list_subtree(company_id, namespace, wiki_page_id)
        page_ids = [item.wiki_page_id for item in subtree]

        for item in subtree:
            await self._rag.remove_page(item)
        await self._repo.soft_delete_pages(company_id, namespace, page_ids)
        await publish_wiki_page_deleted(wiki_page_id, namespace, company_id, page_ids)
        return page_ids

    async def restore_page(
        self, company_id: str, namespace: str, user_id: str, wiki_page_id: str
    ) -> WikiPage:
        await self._repo.restore_pages(company_id, namespace, [wiki_page_id])
        page = await self.require_page(company_id, namespace, wiki_page_id)
        page.last_edited_by_user_id = user_id
        stored = await self._repo.update_page(page)
        await self._rag.index_page(stored)
        await publish_wiki_page_event(
            WIKI_PAGE_RESTORED, self._to_summary(stored, False), company_id
        )
        return stored

    # --- ревизии ---

    async def _store_revision(self, page: WikiPage) -> None:
        revision = WikiRevision(
            wiki_revision_id=_new_id("wrv"),
            wiki_page_id=page.wiki_page_id,
            company_id=page.company_id,
            namespace=page.namespace,
            title=page.title,
            content=page.content,
            text_markdown=page.text_markdown,
            author_user_id=page.last_edited_by_user_id,
            created_at=_utcnow(),
        )
        await self._repo.insert_revision(revision)

    async def list_revisions(
        self, company_id: str, namespace: str, user_id: str, wiki_page_id: str, limit: int = 50
    ) -> list[WikiRevisionSummary]:
        _ = await self.require_viewable_page(company_id, namespace, wiki_page_id, user_id)
        return await self._repo.list_revisions(company_id, namespace, wiki_page_id, limit)

    async def get_revision(
        self, company_id: str, namespace: str, user_id: str, wiki_revision_id: str
    ) -> WikiRevision:
        revision = await self._repo.get_revision(company_id, namespace, wiki_revision_id)
        if revision is None:
            raise WikiPageNotFoundError(f"Ревизия {wiki_revision_id} не найдена")
        _ = await self.require_viewable_page(
            company_id, namespace, revision.wiki_page_id, user_id
        )
        return revision

    async def restore_revision(
        self, company_id: str, namespace: str, user_id: str, wiki_revision_id: str
    ) -> WikiPage:
        revision = await self.get_revision(company_id, namespace, user_id, wiki_revision_id)
        return await self.update_page_content(
            company_id=company_id,
            namespace=namespace,
            user_id=user_id,
            wiki_page_id=revision.wiki_page_id,
            content=revision.content,
            title=revision.title,
        )

    # --- доступ и видимость ---

    async def get_access(
        self, company_id: str, namespace: str, user_id: str, wiki_page_id: str
    ) -> WikiPageAccess:
        page = await self.require_viewable_page(company_id, namespace, wiki_page_id, user_id)
        resolver = await self.build_access_resolver(company_id, namespace, user_id)
        members = await self._repo.list_members(company_id, namespace, wiki_page_id)
        restriction = resolver.nearest_restriction(wiki_page_id)
        return WikiPageAccess(
            wiki_page_id=wiki_page_id,
            visibility=resolver.visibility(wiki_page_id),
            inherited_from_page_id=(
                restriction if restriction is not None and restriction != wiki_page_id else None
            ),
            members=members,
            link_enabled=page.link_enabled,
            link_permission=page.link_permission,
        )

    async def set_member(
        self,
        company_id: str,
        namespace: str,
        user_id: str,
        wiki_page_id: str,
        member_user_id: str,
        permission: WikiPagePermission,
    ) -> WikiPageAccess:
        resolver = await self.build_access_resolver(company_id, namespace, user_id)
        _ = await self.require_page(company_id, namespace, wiki_page_id)
        if not resolver.can_administer(wiki_page_id):
            raise WikiAccessDeniedError(f"Нет прав на изменение доступа {wiki_page_id}")

        await self._repo.upsert_member(
            company_id, namespace, wiki_page_id, member_user_id, permission
        )
        await self._recalculate_visibility(company_id, namespace, wiki_page_id)
        return await self.get_access(company_id, namespace, user_id, wiki_page_id)

    async def remove_member(
        self,
        company_id: str,
        namespace: str,
        user_id: str,
        wiki_page_id: str,
        member_user_id: str,
    ) -> WikiPageAccess:
        resolver = await self.build_access_resolver(company_id, namespace, user_id)
        _ = await self.require_page(company_id, namespace, wiki_page_id)
        if not resolver.can_administer(wiki_page_id):
            raise WikiAccessDeniedError(f"Нет прав на изменение доступа {wiki_page_id}")

        await self._repo.delete_member(company_id, namespace, wiki_page_id, member_user_id)
        await self._recalculate_visibility(company_id, namespace, wiki_page_id)
        return await self.get_access(company_id, namespace, user_id, wiki_page_id)

    async def rotate_public_link(
        self,
        company_id: str,
        namespace: str,
        user_id: str,
        wiki_page_id: str,
        enabled: bool,
        permission: WikiLinkPermission = WikiLinkPermission.VIEW,
    ) -> str | None:
        """Включить, перевыпустить или отключить публичную ссылку.

        Возвращает сырой токен ровно один раз — в базе лежит только его хеш.
        """
        resolver = await self.build_access_resolver(company_id, namespace, user_id)
        _ = await self.require_page(company_id, namespace, wiki_page_id)
        if not resolver.can_administer(wiki_page_id):
            raise WikiAccessDeniedError(f"Нет прав на публикацию ссылки {wiki_page_id}")

        if not enabled:
            await self._repo.set_link_token(
                company_id, namespace, wiki_page_id, None, False, permission
            )
            return None

        raw_token = secrets.token_urlsafe(24)
        await self._repo.set_link_token(
            company_id,
            namespace,
            wiki_page_id,
            _hash_link_token(raw_token),
            True,
            permission,
        )
        return raw_token

    async def _recalculate_visibility(
        self, company_id: str, namespace: str, wiki_page_id: str
    ) -> None:
        """Пересчитать видимость поддерева и перенести индекс.

        Вызывается после любой правки прав или структуры. Перенос индекса
        делается тем же вызовом: разошедшиеся ACL и индекс — это утечка.
        """
        resolver = await self.build_access_resolver(company_id, namespace, None)
        subtree = await self._repo.list_subtree(company_id, namespace, wiki_page_id)
        if not subtree:
            return

        changed: dict[WikiVisibility, list[str]] = {
            WikiVisibility.COMPANY: [],
            WikiVisibility.RESTRICTED: [],
        }
        for item in subtree:
            actual = resolver.visibility(item.wiki_page_id)
            if actual != item.visibility:
                changed[actual].append(item.wiki_page_id)

        if not changed[WikiVisibility.COMPANY] and not changed[WikiVisibility.RESTRICTED]:
            return

        for visibility, page_ids in changed.items():
            await self._repo.set_visibility(company_id, namespace, page_ids, visibility)

        refreshed = await self._repo.list_subtree(company_id, namespace, wiki_page_id)
        moved = [
            item
            for item in refreshed
            if item.wiki_page_id
            in set(changed[WikiVisibility.COMPANY]) | set(changed[WikiVisibility.RESTRICTED])
        ]
        await self._rag.reindex_subtree(moved)
        await publish_wiki_access_changed(
            wiki_page_id,
            namespace,
            company_id,
            resolver.visibility(wiki_page_id),
            [item.wiki_page_id for item in moved],
        )

    async def _apply_depths(
        self,
        company_id: str,
        namespace: str,
        subtree: list[WikiPage],
        root_id: str,
        root_depth: int,
        new_root_page_id: str,
    ) -> None:
        by_parent: dict[str | None, list[WikiPage]] = {}
        for item in subtree:
            by_parent.setdefault(item.parent_page_id, []).append(item)

        depths: dict[str, int] = {root_id: root_depth}
        queue: list[tuple[str, int]] = [(root_id, root_depth)]
        while queue:
            current_id, current_depth = queue.pop()
            for child in by_parent.get(current_id, []):
                depths[child.wiki_page_id] = current_depth + 1
                queue.append((child.wiki_page_id, current_depth + 1))

        await self._repo.apply_subtree_depth(company_id, namespace, depths, new_root_page_id)

    # --- ссылки ---

    async def _sync_links(self, page: WikiPage) -> None:
        extracted = extract_links(page.content)
        now = _utcnow()
        links = [
            WikiPageLink(
                wiki_page_link_id=_new_id("wlk"),
                company_id=page.company_id,
                namespace=page.namespace,
                source_page_id=page.wiki_page_id,
                target_kind=item.target_kind,
                target_id=item.target_id,
                target_label=item.target_label,
                created_at=now,
            )
            for item in extracted
        ]
        await self._repo.replace_page_links(
            page.company_id, page.namespace, page.wiki_page_id, links
        )

    async def list_backlinks(
        self,
        company_id: str,
        user_id: str,
        target_kind: WikiLinkTargetKind,
        target_id: str,
        limit: int = 50,
    ) -> list[WikiBacklink]:
        """Обратные ссылки на сущность из всех доступных пользователю пространств."""
        raw = await self._repo.list_backlinks(company_id, target_kind, target_id, limit)
        by_namespace: dict[str, list[WikiBacklink]] = {}
        for item in raw:
            by_namespace.setdefault(item.namespace, []).append(item)

        allowed: list[WikiBacklink] = []
        for namespace, items in by_namespace.items():
            resolver = await self.build_access_resolver(company_id, namespace, user_id)
            allowed.extend(item for item in items if resolver.can_view(item.wiki_page_id))
        return allowed

    def mentioned_users(self, page: WikiPage) -> list[ExtractedMention]:
        return extract_user_mentions(page.content)

    # --- поиск ---

    async def search_pages(
        self, company_id: str, namespace: str, user_id: str, query: str, limit: int = 20
    ) -> list[WikiSearchHit]:
        resolver = await self.build_access_resolver(company_id, namespace, user_id)
        tree = await self._repo.list_tree(company_id, namespace)
        allowed = [item.wiki_page_id for item in tree if resolver.can_view(item.wiki_page_id)]
        if not allowed:
            return []
        return await self._repo.search_pages(company_id, namespace, query, limit, allowed)

    async def accessible_page_ids(
        self, company_id: str, namespace: str, user_id: str
    ) -> list[str]:
        resolver = await self.build_access_resolver(company_id, namespace, user_id)
        tree = await self._repo.list_tree(company_id, namespace)
        return [item.wiki_page_id for item in tree if resolver.can_view(item.wiki_page_id)]

    async def semantic_search(
        self,
        company_id: str,
        namespace: str,
        user_id: str,
        query: str,
        limit: int = 20,
        root_page_id: str | None = None,
        published_only: bool = False,
        updated_after: datetime | None = None,
        editor_user_id: str | None = None,
    ) -> list[WikiSearchHit]:
        """Смысловой поиск по страницам пространства.

        Ограниченные страницы попадают в выдачу только через явный список
        разрешённых идентификаторов. Если список оказался длиннее предела
        фильтра, поиск сужается до общедоступного слоя, а не молча теряет
        часть результатов.
        """
        resolver = await self.build_access_resolver(company_id, namespace, user_id)
        tree = await self._repo.list_tree(company_id, namespace)
        restricted_visible = [
            item.wiki_page_id
            for item in tree
            if item.visibility == WikiVisibility.RESTRICTED
            and resolver.can_view(item.wiki_page_id)
        ]

        spec = WikiSearchFilter(
            namespace=namespace,
            root_page_id=root_page_id,
            published_only=published_only,
            updated_after=updated_after,
            editor_user_id=editor_user_id,
        )
        try:
            base_filter = build_wiki_search_filter(spec)
            filters: RAGMetadataFilter = base_filter
            if restricted_visible:
                ensure_page_filter_size(len(restricted_visible), "доступных")
                company_branch: RAGMetadataFilter = {
                    "$and": [
                        base_filter,
                        {"wiki_visibility": {"$eq": WikiVisibility.COMPANY.value}},
                    ]
                }
                restricted_branch: RAGMetadataFilter = {
                    "$and": [
                        base_filter,
                        {"wiki_page_id": {"$in": list(restricted_visible)}},
                    ]
                }
                filters = {"$or": [company_branch, restricted_branch]}
        except WikiRagFilterOverflowError:
            logger.warning(
                "wiki.search.restricted_filter_overflow",
                extra={"namespace": namespace, "restricted": len(restricted_visible)},
            )
            spec.visibility = WikiVisibility.COMPANY
            filters = build_wiki_search_filter(spec)

        results = await self._rag.search(
            namespace,
            query,
            limit,
            filters,
            include_restricted=bool(restricted_visible),
        )
        titles = {item.wiki_page_id: item for item in tree}

        hits: list[WikiSearchHit] = []
        for result in results:
            page_id = result.document_id
            summary = titles.get(page_id)
            if summary is None or not resolver.can_view(page_id):
                continue
            raw_heading = result.metadata.get("wiki_heading_path")
            hits.append(
                WikiSearchHit(
                    wiki_page_id=page_id,
                    namespace=namespace,
                    title=summary.title,
                    icon=summary.icon,
                    snippet=result.content[:280],
                    heading_path=raw_heading if isinstance(raw_heading, str) else "",
                    score=result.score,
                    updated_at=summary.updated_at,
                )
            )
        return hits

    # --- комментарии ---

    async def list_comments(
        self, company_id: str, namespace: str, user_id: str, wiki_page_id: str
    ) -> list[WikiComment]:
        _ = await self.require_viewable_page(company_id, namespace, wiki_page_id, user_id)
        return await self._repo.list_comments(company_id, namespace, wiki_page_id)

    async def create_comment(
        self,
        company_id: str,
        namespace: str,
        user_id: str,
        wiki_page_id: str,
        body_markdown: str,
        anchor_text: str = "",
        parent_comment_id: str | None = None,
    ) -> WikiComment:
        _ = await self.require_viewable_page(company_id, namespace, wiki_page_id, user_id)
        now = _utcnow()
        comment = WikiComment(
            wiki_comment_id=_new_id("wcm"),
            wiki_page_id=wiki_page_id,
            company_id=company_id,
            namespace=namespace,
            parent_comment_id=parent_comment_id,
            author_user_id=user_id,
            body_markdown=body_markdown,
            anchor_text=anchor_text,
            created_at=now,
            updated_at=now,
        )
        stored = await self._repo.insert_comment(comment)
        await publish_wiki_comment_event(WIKI_COMMENT_CREATED, stored, company_id)
        return stored

    async def resolve_comment(
        self,
        company_id: str,
        namespace: str,
        user_id: str,
        wiki_comment_id: str,
        resolved: bool,
    ) -> WikiComment:
        stored = await self._repo.resolve_comment(
            company_id, namespace, wiki_comment_id, user_id if resolved else None
        )
        if stored is None:
            raise WikiPageNotFoundError(f"Комментарий {wiki_comment_id} не найден")
        await publish_wiki_comment_event(WIKI_COMMENT_RESOLVED, stored, company_id)
        return stored

    async def delete_comment(
        self, company_id: str, namespace: str, user_id: str, wiki_comment_id: str
    ) -> None:
        _ = user_id
        await self._repo.delete_comment(company_id, namespace, wiki_comment_id)

    # --- вспомогательное ---

    def _to_summary(self, page: WikiPage, has_children: bool) -> WikiPageSummary:
        return WikiPageSummary(
            wiki_page_id=page.wiki_page_id,
            namespace=page.namespace,
            parent_page_id=page.parent_page_id,
            root_page_id=page.root_page_id,
            depth=page.depth,
            position=page.position,
            title=page.title,
            icon=page.icon,
            visibility=page.visibility,
            is_published=page.is_published,
            is_template=page.is_template,
            has_children=has_children,
            updated_at=page.updated_at,
            last_edited_by_user_id=page.last_edited_by_user_id,
        )

    async def list_members(
        self, company_id: str, namespace: str, wiki_page_id: str
    ) -> list[WikiPageMember]:
        return await self._repo.list_members(company_id, namespace, wiki_page_id)


__all__ = [
    "WikiAccessDeniedError",
    "WikiPageNotFoundError",
    "WikiService",
]
