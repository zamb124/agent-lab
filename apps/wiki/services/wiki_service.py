"""
Бизнес-логика wiki.

Единственная точка записи страницы. Здесь и только здесь:

* из `content` выводится `text_markdown` — снаружи это поле не пишется;
* пересчитывается материализация `company_visible` поддерева и переносится
  индекс RAG;
* переписываются исходящие ссылки и публикуются доменные события.

Namespace передаётся во все методы явно и уходит в каждый запрос репозитория:
операции «по одному id» без пространства не существует.

Права — единственный источник истины OpenFGA (`AuthzService`). SQL
`company_visible` на странице — материализация FGA `company_viewer`
(`company#member`) для дешёвого выбора RAG-слоя; PDP-решения принимает
только `AuthzService`. `company` tuple — tenancy, сам доступ не даёт.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime

from apps.wiki.content.markdown_file import (
    WikiMarkdownFrontMatter,
    compose_markdown_file,
    split_markdown_file,
)
from apps.wiki.content.markdown_notices import WikiMarkdownNotice
from apps.wiki.content.markdown_parser import parse_markdown
from apps.wiki.content.markdown_serializer import document_to_markdown
from apps.wiki.content.prosemirror import ProseMirrorNode, empty_document
from apps.wiki.content.public_media import collect_file_ids, platform_file_id_from_url
from apps.wiki.content.schema import normalize_document
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
from apps.wiki.models.api import WikiPageResponse
from apps.wiki.models.domain import (
    WikiAccessMemberRelation,
    WikiBacklink,
    WikiComment,
    WikiLinkPermission,
    WikiLinkTargetKind,
    WikiPage,
    WikiPageAccess,
    WikiPageLink,
    WikiPageMember,
    WikiPageSummary,
    WikiRevision,
    WikiRevisionSummary,
    WikiSearchHit,
)
from apps.wiki.services.links import ExtractedMention, extract_links, extract_user_mentions
from apps.wiki.services.rag_index import WikiRagIndexService
from apps.wiki.services.rag_metadata import (
    WikiRagFilterOverflowError,
    WikiSearchFilter,
    build_wiki_search_filter,
    ensure_page_filter_size,
)
from apps.wiki.services.wiki_access_service import WikiAccessService
from core.auth.utils import hash_token
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation
from core.errors.boundary import PlatformAccessDeniedError, PlatformNotFoundError
from core.logging import get_logger
from core.utils.time import utcnow

logger = get_logger(__name__)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


class WikiService:
    """Операции над страницами и их окружением."""

    def __init__(
        self,
        rag_index: WikiRagIndexService,
        access: WikiAccessService,
        authz: AuthzService,
    ) -> None:
        self._rag: WikiRagIndexService = rag_index
        self._access: WikiAccessService = access
        self._authz: AuthzService = authz

    # --- доступ ---

    async def require_page(self, company_id: str, namespace: str, wiki_page_id: str) -> WikiPage:
        page = await WikiPage.alive_page(company_id, namespace, wiki_page_id)
        if page is None:
            raise PlatformNotFoundError(f"Page {wiki_page_id} not found in {namespace}", error_code="not_found")
        return page

    async def page_response(self, page: WikiPage, *, user_id: str) -> WikiPageResponse:
        """can_edit / can_admin только из AuthzService (включая mutating-ответы)."""
        obj = AuthzObject.wiki_page(page.wiki_page_id)
        can_edit = await self._authz.can_edit(obj, user_id=user_id)
        can_admin = await self._authz.can_admin(obj, user_id=user_id)
        return WikiPageResponse(page=page, can_edit=can_edit, can_admin=can_admin)

    async def require_viewable_page(
        self, company_id: str, namespace: str, wiki_page_id: str, user_id: str
    ) -> WikiPage:
        page = await self.require_page(company_id, namespace, wiki_page_id)
        try:
            await self._authz.require_can_view(AuthzObject.wiki_page(wiki_page_id), user_id=user_id)
        except AuthzDenied as exc:
            raise PlatformAccessDeniedError(f"No access to page {wiki_page_id}", error_code="forbidden") from exc
        return page

    async def require_editable_page(
        self, company_id: str, namespace: str, wiki_page_id: str, user_id: str
    ) -> WikiPage:
        page = await self.require_page(company_id, namespace, wiki_page_id)
        try:
            await self._authz.require_can_edit(AuthzObject.wiki_page(wiki_page_id), user_id=user_id)
        except AuthzDenied as exc:
            raise PlatformAccessDeniedError(
                f"No permission to edit page {wiki_page_id}",
                error_code="forbidden",
            ) from exc
        return page

    # --- чтение ---

    async def list_tree(
        self, company_id: str, namespace: str, user_id: str
    ) -> list[WikiPageSummary]:
        tree = await WikiPage.list_tree(company_id, namespace)
        allowed = set(
            await self._access.filter_viewable_page_ids(
                [item.wiki_page_id for item in tree], user_id=user_id
            )
        )
        return [item for item in tree if item.wiki_page_id in allowed]

    async def list_deleted(self, company_id: str, namespace: str) -> list[WikiPageSummary]:
        """Корзина пространства: удаление зачищает FGA-tuples страницы,

        поэтому доступ к корзине определяется одной проверкой членства в
        namespace (`require_namespace` + `platform_namespace` viewer), не FGA
        per-page `can_view` — его после удаления не осталось ни у кого, включая владельца.
        """
        pages = await WikiPage.list_deleted(company_id, namespace)
        return [self._to_summary(page, False) for page in pages]

    async def get_public_site_tree(self, raw_token: str) -> list[WikiPageSummary]:
        """Навигация публичного сайта.

        Токен живёт на корне, а сайт — это его опубликованное поддерево. Пустой
        список значит, что сайта по такому токену нет: корень всегда входит в
        свою же навигацию.
        """
        root = await WikiPage.get_public_page(raw_token)
        if root is None:
            return []
        return await WikiPage.list_public_subtree(
            root.company_id, root.namespace, root.wiki_page_id
        )

    async def get_public_site_page(self, raw_token: str, wiki_page_id: str) -> WikiPage | None:
        """Страница сайта по её id.

        Доступна только страница из опубликованного поддерева корня: снятая с
        публикации ветка не отдаётся даже по прямому id.
        """
        root = await WikiPage.get_public_page(raw_token)
        if root is None:
            return None
        if wiki_page_id == root.wiki_page_id:
            return root
        published = await WikiPage.list_public_subtree(
            root.company_id, root.namespace, root.wiki_page_id
        )
        if all(item.wiki_page_id != wiki_page_id for item in published):
            return None
        return await WikiPage.alive_page(root.company_id, root.namespace, wiki_page_id)

    async def public_site_has_file(self, raw_token: str, file_id: str) -> bool:
        """Встречается ли файл в содержимом страниц сайта.

        Это вся авторизация гостевой выдачи файла: посторонний `file_id`, даже
        принадлежащий той же компании, по ссылке сайта не отдаётся.
        """
        root = await WikiPage.get_public_page(raw_token)
        if root is None:
            return False
        published_ids = {
            item.wiki_page_id
            for item in await WikiPage.list_public_subtree(
                root.company_id, root.namespace, root.wiki_page_id
            )
        }
        pages = await WikiPage.list_subtree(root.company_id, root.namespace, root.wiki_page_id)
        for page in pages:
            if page.wiki_page_id not in published_ids:
                continue
            if file_id in collect_file_ids(page.content):
                return True
            if platform_file_id_from_url(page.cover_url) == file_id:
                return True
        return False

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
        now = utcnow()
        wiki_page_id = _new_id("wpg")
        position = await WikiPage.next_position(company_id, namespace, parent_page_id)

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
            company_visible=parent.company_visible if parent is not None else True,
            created_by_user_id=user_id,
            last_edited_by_user_id=user_id,
            published_at=now,
            created_at=now,
            updated_at=now,
        )

        stored = await WikiPage.create_page(page)
        try:
            await self._access.sync_page_created(
                stored, owner_user_id=user_id, company_visible=stored.company_visible
            )
        except Exception:
            await WikiPage.delete_page_in_namespace(
                company_id,
                namespace,
                stored.wiki_page_id,
            )
            raise
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

        stored = await WikiPage.update_existing(page)
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
        is_full_width: bool | None = None,
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
                page.published_at = utcnow()
        if is_template is not None:
            page.is_template = is_template
        if is_full_width is not None:
            page.is_full_width = is_full_width
        page.last_edited_by_user_id = user_id

        stored = await WikiPage.update_existing(page)
        await self._rag.index_page(stored)
        await publish_wiki_page_event(
            WIKI_PAGE_UPDATED, self._to_summary(stored, False), company_id
        )
        return stored

    # --- markdown ---

    async def import_markdown(
        self,
        company_id: str,
        namespace: str,
        user_id: str,
        markdown: str,
        wiki_page_id: str | None = None,
        parent_page_id: str | None = None,
        apply_front_matter: bool = True,
    ) -> tuple[WikiPage, list[WikiMarkdownNotice]]:
        """Импортировать markdown-файл в страницу.

        Без `wiki_page_id` создаётся новая страница, с ним — заменяется
        содержимое существующей. Заметки о том, что не перенеслось, возвращаются
        наверх: пользователь должен увидеть расхождение, а не обнаружить его
        через месяц.
        """
        parts = split_markdown_file(markdown)
        parsed = parse_markdown(parts.body)
        notices = [*parts.notices, *parsed.notices]
        front_matter = parts.front_matter if apply_front_matter else WikiMarkdownFrontMatter()

        if wiki_page_id is None:
            page = await self.create_page(
                company_id=company_id,
                namespace=namespace,
                user_id=user_id,
                title=front_matter.title if front_matter.title is not None else "",
                parent_page_id=parent_page_id,
                content=parsed.document,
                icon=front_matter.icon if front_matter.icon is not None else "",
            )
        else:
            page = await self.update_page_content(
                company_id=company_id,
                namespace=namespace,
                user_id=user_id,
                wiki_page_id=wiki_page_id,
                content=parsed.document,
                title=front_matter.title,
            )

        # Иконку новой страницы проставил `create_page`; обложка живёт только в
        # свойствах, поэтому её всегда дописывает отдельный вызов.
        icon_update = front_matter.icon if wiki_page_id is not None else None
        if icon_update is not None or front_matter.cover_url is not None:
            page = await self.update_page_properties(
                company_id=company_id,
                namespace=namespace,
                user_id=user_id,
                wiki_page_id=page.wiki_page_id,
                icon=icon_update,
                cover_url=front_matter.cover_url,
            )

        if notices:
            logger.info(
                "wiki.markdown_import.notices",
                wiki_page_id=page.wiki_page_id,
                namespace=namespace,
                notice_count=len(notices),
                notice_kinds=sorted({notice.kind.value for notice in notices}),
            )
        return page, notices

    def export_markdown_file(self, page: WikiPage) -> str:
        """Файл для выгрузки: свойства страницы в YAML-шапке плюс содержимое."""
        return compose_markdown_file(
            title=page.title,
            icon=page.icon,
            cover_url=page.cover_url,
            body=page.text_markdown,
        )

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
        subtree = await WikiPage.list_subtree(company_id, namespace, wiki_page_id)
        subtree_ids = {item.wiki_page_id for item in subtree}

        if new_parent_page_id is not None:
            if new_parent_page_id in subtree_ids:
                raise ValueError("Cannot move a page into its own subtree")
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
            else await WikiPage.next_position(company_id, namespace, new_parent_page_id)
        )

        await WikiPage.update_page_location(
            company_id=company_id,
            namespace=namespace,
            wiki_page_id=wiki_page_id,
            parent_page_id=new_parent_page_id,
            root_page_id=new_root,
            position=target_position,
            updated_at=utcnow(),
        )
        await self._apply_depths(company_id, namespace, subtree, wiki_page_id, new_depth, new_root)
        await self._access.sync_page_moved(
            wiki_page_id,
            old_parent_page_id=previous_parent,
            new_parent_page_id=new_parent_page_id,
        )
        await self._recalculate_company_visible(company_id, namespace, wiki_page_id)

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
            raise ValueError("Target workspace is the same as the current one")

        page = await self.require_editable_page(company_id, namespace, wiki_page_id, user_id)
        subtree = await WikiPage.list_subtree(company_id, namespace, wiki_page_id)
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

        await WikiPage.move_subtree_to_namespace(
            company_id=company_id,
            source_namespace=namespace,
            target_namespace=target_namespace,
            page_ids=subtree_ids,
            root_page_id=new_root,
            depth_shift=new_depth - page.depth,
            new_parent_page_id=new_parent_page_id,
            moved_page_id=wiki_page_id,
        )
        await self._access.sync_page_moved(
            wiki_page_id,
            old_parent_page_id=page.parent_page_id,
            new_parent_page_id=new_parent_page_id,
        )

        moved_subtree = await WikiPage.list_subtree(company_id, target_namespace, wiki_page_id)
        await self._recalculate_company_visible(company_id, target_namespace, wiki_page_id)
        refreshed = await WikiPage.list_subtree(company_id, target_namespace, wiki_page_id)
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
        _ = await self.require_page(company_id, namespace, wiki_page_id)
        try:
            await self._authz.require_can_admin(
                AuthzObject.wiki_page(wiki_page_id), user_id=user_id
            )
        except AuthzDenied as exc:
            raise PlatformAccessDeniedError(
                f"No permission to delete page {wiki_page_id}",
                error_code="forbidden",
            ) from exc

        subtree = await WikiPage.list_subtree(company_id, namespace, wiki_page_id)
        page_ids = [item.wiki_page_id for item in subtree]

        for item in subtree:
            await self._rag.remove_page(item)
        if len(page_ids) > 0:
            await WikiPage.mark_pages_deleted(
                company_id=company_id,
                namespace=namespace,
                wiki_page_ids=page_ids,
                deleted_at=utcnow(),
            )
        await self._access.sync_pages_deleted(page_ids)
        await publish_wiki_page_deleted(wiki_page_id, namespace, company_id, page_ids)
        return page_ids

    async def restore_page(
        self, company_id: str, namespace: str, user_id: str, wiki_page_id: str
    ) -> WikiPage:
        """Восстановить страницу из корзины.

        Удаление зачищает все FGA-tuples страницы (`sync_pages_deleted`), так
        что восстановление обязано пересобрать owner/parent/company заново —
        иначе восстановленная страница осталась бы без единого администратора.
        """
        await WikiPage.set_deleted_at(
            company_id=company_id,
            namespace=namespace,
            wiki_page_id=wiki_page_id,
            deleted_at=None,
        )
        page = await self.require_page(company_id, namespace, wiki_page_id)
        page.last_edited_by_user_id = user_id
        stored = await WikiPage.update_existing(page)
        try:
            await self._access.sync_page_created(
                stored,
                owner_user_id=stored.created_by_user_id,
                company_visible=stored.company_visible,
            )
        except Exception:
            await WikiPage.set_deleted_at(
                company_id=company_id,
                namespace=namespace,
                wiki_page_id=wiki_page_id,
                deleted_at=utcnow(),
            )
            raise
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
            created_at=utcnow(),
        )
        _ = await WikiRevision.store_revision(revision)

    async def list_revisions(
        self, company_id: str, namespace: str, user_id: str, wiki_page_id: str, limit: int = 50
    ) -> list[WikiRevisionSummary]:
        _ = await self.require_viewable_page(company_id, namespace, wiki_page_id, user_id)
        rows = await WikiRevision.list_revisions(
            company_id,
            namespace,
            wiki_page_id,
            limit=limit,
        )
        return [
            WikiRevisionSummary(
                wiki_revision_id=row.wiki_revision_id,
                wiki_page_id=row.wiki_page_id,
                title=row.title,
                author_user_id=row.author_user_id,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def get_revision(
        self, company_id: str, namespace: str, user_id: str, wiki_revision_id: str
    ) -> WikiRevision:
        revision = await WikiRevision.get_revision(
            company_id,
            namespace,
            wiki_revision_id,
        )
        if revision is None:
            raise PlatformNotFoundError(f"Revision {wiki_revision_id} not found", error_code="not_found")
        _ = await self.require_viewable_page(company_id, namespace, revision.wiki_page_id, user_id)
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
        tree = await WikiPage.list_tree(company_id, namespace)
        parents = {item.wiki_page_id: item.parent_page_id for item in tree}
        company_visible_by_id = {item.wiki_page_id: item.company_visible for item in tree}
        restriction_root = await self._access.inherited_restriction_root(
            wiki_page_id,
            parents=parents,
            company_visible_by_id=company_visible_by_id,
        )
        inherited_from = (
            restriction_root
            if restriction_root is not None and restriction_root != wiki_page_id
            else None
        )
        return await self._access.build_access(page, inherited_from_page_id=inherited_from)

    async def set_member(
        self,
        company_id: str,
        namespace: str,
        user_id: str,
        wiki_page_id: str,
        member_user_id: str,
        relation: WikiAccessMemberRelation,
    ) -> WikiPageAccess:
        page = await self.require_page(company_id, namespace, wiki_page_id)
        try:
            await self._authz.require_relation(
                AuthzRelation.CAN_SHARE,
                AuthzObject.wiki_page(wiki_page_id),
                user_id=user_id,
            )
        except AuthzDenied as exc:
            raise PlatformAccessDeniedError(
                f"No permission to change access {wiki_page_id}",
                error_code="forbidden",
            ) from exc
        if page.company_visible:
            raise ValueError(
                "Page is visible to the whole company; members can be added only after "
                + "restricting access"
            )

        await self._access.add_member(wiki_page_id, user_id=member_user_id, relation=relation)
        return await self.get_access(company_id, namespace, user_id, wiki_page_id)

    async def remove_member(
        self,
        company_id: str,
        namespace: str,
        user_id: str,
        wiki_page_id: str,
        member_user_id: str,
    ) -> WikiPageAccess:
        _ = await self.require_page(company_id, namespace, wiki_page_id)
        try:
            await self._authz.require_relation(
                AuthzRelation.CAN_SHARE,
                AuthzObject.wiki_page(wiki_page_id),
                user_id=user_id,
            )
        except AuthzDenied as exc:
            raise PlatformAccessDeniedError(
                f"No permission to change access {wiki_page_id}",
                error_code="forbidden",
            ) from exc

        await self._access.remove_member(wiki_page_id, user_id=member_user_id)
        return await self.get_access(company_id, namespace, user_id, wiki_page_id)

    async def set_company_visible(
        self,
        company_id: str,
        namespace: str,
        user_id: str,
        wiki_page_id: str,
        company_visible: bool,
    ) -> WikiPageAccess:
        """Переключить страницу между «вся компания» и «по участникам».

        Включение company-visible снимает всех явных участников: смысл этого
        режима — доступ всей компании, а не компания плюс отдельный список.
        """
        _ = await self.require_page(company_id, namespace, wiki_page_id)
        try:
            await self._authz.require_relation(
                AuthzRelation.CAN_SHARE,
                AuthzObject.wiki_page(wiki_page_id),
                user_id=user_id,
            )
        except AuthzDenied as exc:
            raise PlatformAccessDeniedError(
                f"No permission to change access {wiki_page_id}",
                error_code="forbidden",
            ) from exc

        if company_visible:
            await self._access.clear_members(wiki_page_id)
        await self._access.set_company_visible(
            wiki_page_id, company_id, company_visible=company_visible
        )
        await self._recalculate_company_visible(company_id, namespace, wiki_page_id)
        return await self.get_access(company_id, namespace, user_id, wiki_page_id)

    async def rotate_public_link(
        self,
        company_id: str,
        namespace: str,
        user_id: str,
        wiki_page_id: str,
        enabled: bool,
        permission: WikiLinkPermission = WikiLinkPermission.VIEWER,
    ) -> str | None:
        """Включить, перевыпустить или отключить публичную ссылку.

        Возвращает сырой токен ровно один раз — в базе лежит только его хеш.
        """
        _ = await self.require_page(company_id, namespace, wiki_page_id)
        try:
            await self._authz.require_relation(
                AuthzRelation.CAN_SHARE,
                AuthzObject.wiki_page(wiki_page_id),
                user_id=user_id,
            )
        except AuthzDenied as exc:
            raise PlatformAccessDeniedError(
                f"No permission to publish a link {wiki_page_id}",
                error_code="forbidden",
            ) from exc

        if not enabled:
            await WikiPage.write_link_token(
                company_id, namespace, wiki_page_id, None, False, permission
            )
            return None

        raw_token = secrets.token_urlsafe(24)
        await WikiPage.write_link_token(
            company_id,
            namespace,
            wiki_page_id,
            hash_token(raw_token),
            True,
            permission,
        )
        return raw_token

    async def _recalculate_company_visible(
        self, company_id: str, namespace: str, wiki_page_id: str
    ) -> None:
        """Сверить SQL `company_visible` с FGA `company_viewer` tuple по поддереву.

        `company_visible` в БД — материализация FGA для RAG, PDP-решения через
        неё не принимаются. Вызывается после любой правки company/members или
        переноса страницы: расхождение синхронизируется, а изменившиеся
        страницы переносятся между слоями индекса тем же вызовом — разошедшиеся
        ACL и индекс это утечка.
        """
        subtree = await WikiPage.list_subtree(company_id, namespace, wiki_page_id)
        if not subtree:
            return

        changed_to_true: list[str] = []
        changed_to_false: list[str] = []
        for item in subtree:
            actual = await self._access.page_is_company_visible(item.wiki_page_id, company_id)
            if actual == item.company_visible:
                continue
            (changed_to_true if actual else changed_to_false).append(item.wiki_page_id)

        if not changed_to_true and not changed_to_false:
            return

        if len(changed_to_true) > 0:
            await WikiPage.write_company_visible(company_id, namespace, changed_to_true, True)
        if len(changed_to_false) > 0:
            await WikiPage.write_company_visible(company_id, namespace, changed_to_false, False)

        changed_ids = set(changed_to_true) | set(changed_to_false)
        refreshed = await WikiPage.list_subtree(company_id, namespace, wiki_page_id)
        moved = [item for item in refreshed if item.wiki_page_id in changed_ids]
        await self._rag.reindex_subtree(moved)

        root = await self.require_page(company_id, namespace, wiki_page_id)
        await publish_wiki_access_changed(
            wiki_page_id,
            namespace,
            company_id,
            root.rag_visibility,
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

        await WikiPage.apply_depths(
            company_id=company_id,
            namespace=namespace,
            depths=depths,
            root_page_id=new_root_page_id,
        )

    # --- ссылки ---

    async def _sync_links(self, page: WikiPage) -> None:
        extracted = extract_links(page.content)
        now = utcnow()
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
        await WikiPageLink.sync_links(
            company_id=page.company_id,
            namespace=page.namespace,
            source_page_id=page.wiki_page_id,
            links=links,
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
        raw = await self._backlinks(company_id, target_kind, target_id, limit)
        by_namespace: dict[str, list[WikiBacklink]] = {}
        for item in raw:
            by_namespace.setdefault(item.namespace, []).append(item)

        allowed: list[WikiBacklink] = []
        for items in by_namespace.values():
            allowed_ids = set(
                await self._access.filter_viewable_page_ids(
                    [item.wiki_page_id for item in items], user_id=user_id
                )
            )
            allowed.extend(item for item in items if item.wiki_page_id in allowed_ids)
        return allowed

    def mentioned_users(self, page: WikiPage) -> list[ExtractedMention]:
        return extract_user_mentions(page.content)

    # --- поиск ---

    async def search_pages(
        self, company_id: str, namespace: str, user_id: str, query: str, limit: int = 20
    ) -> list[WikiSearchHit]:
        tree = await WikiPage.list_tree(company_id, namespace)
        allowed = await self._access.filter_viewable_page_ids(
            [item.wiki_page_id for item in tree], user_id=user_id
        )
        if not allowed:
            return []
        return await WikiPage.search_pages(company_id, namespace, query, limit, allowed)

    async def accessible_page_ids(self, company_id: str, namespace: str, user_id: str) -> list[str]:
        tree = await WikiPage.list_tree(company_id, namespace)
        return await self._access.filter_viewable_page_ids(
            [item.wiki_page_id for item in tree], user_id=user_id
        )

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

        Кандидатный set всегда фильтруется через Authz (`filter_viewable_page_ids`).
        SQL `company_visible` — только RAG metadata / restricted namespace, не ACL.
        """
        tree = await WikiPage.list_tree(company_id, namespace)
        tree_ids = [item.wiki_page_id for item in tree]
        allowed_ids = set(await self._access.filter_viewable_page_ids(tree_ids, user_id=user_id))
        if not allowed_ids:
            return []

        allowed_list = list(allowed_ids)
        has_restricted_access = any(
            (not item.company_visible) and item.wiki_page_id in allowed_ids for item in tree
        )

        spec = WikiSearchFilter(
            namespace=namespace,
            root_page_id=root_page_id,
            published_only=published_only,
            updated_after=updated_after,
            editor_user_id=editor_user_id,
            allowed_page_ids=allowed_list,
        )
        try:
            ensure_page_filter_size(len(allowed_list), "доступных")
            filters = build_wiki_search_filter(spec)
        except WikiRagFilterOverflowError:
            logger.warning(
                "wiki.search.allowed_filter_overflow",
                extra={"namespace": namespace, "allowed": len(allowed_list)},
            )
            raise

        results = await self._rag.search(
            namespace,
            query,
            limit,
            filters,
            include_restricted=has_restricted_access,
        )
        titles = {item.wiki_page_id: item for item in tree}

        hits: list[WikiSearchHit] = []
        for result in results:
            page_id = result.document_id
            summary = titles.get(page_id)
            if summary is None or page_id not in allowed_ids:
                continue
            raw_heading = result.attributes.get("wiki_heading_path")
            hits.append(
                WikiSearchHit(
                    wiki_page_id=page_id,
                    namespace=namespace,
                    title=summary.title,
                    icon=summary.icon,
                    snippet=result.content[:280],
                    heading_path=raw_heading if isinstance(raw_heading, str) else "",
                    score=result.score,
                    channel="semantic",
                    updated_at=summary.updated_at,
                )
            )
        return hits

    # --- комментарии ---

    async def list_comments(
        self, company_id: str, namespace: str, user_id: str, wiki_page_id: str
    ) -> list[WikiComment]:
        _ = await self.require_viewable_page(company_id, namespace, wiki_page_id, user_id)
        return await WikiComment.list_comments(company_id, namespace, wiki_page_id)

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
        now = utcnow()
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
        stored = await WikiComment.create_comment(comment)
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
        stored = await WikiComment.get_comment(company_id, namespace, wiki_comment_id)
        if stored is None:
            raise PlatformNotFoundError(f"Comment {wiki_comment_id} not found", error_code="not_found")
        stored.resolved_by_user_id = user_id if resolved else None
        stored.resolved_at = utcnow() if resolved else None
        _ = await stored.save()
        await publish_wiki_comment_event(WIKI_COMMENT_RESOLVED, stored, company_id)
        return stored

    async def delete_comment(
        self, company_id: str, namespace: str, user_id: str, wiki_comment_id: str
    ) -> None:
        _ = user_id
        deleted_count = await WikiComment.delete_comment(
            company_id,
            namespace,
            wiki_comment_id,
        )
        if deleted_count == 0:
            raise PlatformNotFoundError(f"Comment {wiki_comment_id} not found", error_code="not_found")

    # --- вспомогательное ---

    async def _backlinks(
        self,
        company_id: str,
        target_kind: WikiLinkTargetKind,
        target_id: str,
        limit: int,
    ) -> list[WikiBacklink]:
        links = await WikiPageLink.list_backlinks(
            company_id,
            target_kind,
            target_id,
        )
        if len(links) == 0:
            return []
        pages = await WikiPage.list_alive(
            company_id,
            [link.source_page_id for link in links],
        )
        by_id = {page.wiki_page_id: page for page in pages}
        hits: list[WikiBacklink] = []
        for link in links:
            page = by_id.get(link.source_page_id)
            if page is None:
                continue
            hits.append(
                WikiBacklink(
                    wiki_page_id=page.wiki_page_id,
                    namespace=page.namespace,
                    title=page.title,
                    icon=page.icon,
                    target_kind=link.target_kind,
                    target_id=link.target_id,
                    updated_at=page.updated_at,
                )
            )
        hits.sort(key=lambda item: item.updated_at, reverse=True)
        return hits[:limit]

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
            company_visible=page.company_visible,
            is_published=page.is_published,
            is_template=page.is_template,
            has_children=has_children,
            updated_at=page.updated_at,
            last_edited_by_user_id=page.last_edited_by_user_id,
        )

    async def list_members(self, wiki_page_id: str) -> list[WikiPageMember]:
        return await self._access.list_member_items(wiki_page_id)


__all__ = ["WikiService"]
