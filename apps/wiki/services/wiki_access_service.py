"""Wiki access: OpenFGA sole PDP + public link token AuthN (link_* on page row)."""

from __future__ import annotations

from datetime import datetime, timezone

from apps.wiki.authz.tuples import (
    wiki_page_company_link,
    wiki_page_company_viewer_tuple,
    wiki_page_member_tuple,
    wiki_page_owner_tuple,
    wiki_page_parent_tuple,
)
from apps.wiki.models.domain import (
    WikiAccessMemberRelation,
    WikiPage,
    WikiPageAccess,
    WikiPageMember,
)
from core.authz.models import AuthzCheckItem, AuthzObject, AuthzSubject, AuthzTuple
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation, AuthzSubjectKind

_MEMBER_RELATIONS: tuple[AuthzRelation, ...] = (
    AuthzRelation.VIEWER,
    AuthzRelation.EDITOR,
)


def _relation_wire(relation: AuthzRelation) -> WikiAccessMemberRelation:
    if relation is AuthzRelation.VIEWER:
        return "viewer"
    if relation is AuthzRelation.EDITOR:
        return "editor"
    raise ValueError(f"unsupported wiki member relation: {relation}")


def _relation_authz(relation: WikiAccessMemberRelation) -> AuthzRelation:
    if relation == "viewer":
        return AuthzRelation.VIEWER
    return AuthzRelation.EDITOR


class WikiAccessService:
    def __init__(self, authz: AuthzService) -> None:
        self._authz: AuthzService = authz

    def _obj(self, wiki_page_id: str) -> AuthzObject:
        return AuthzObject.wiki_page(wiki_page_id)

    async def sync_page_created(
        self,
        page: WikiPage,
        *,
        owner_user_id: str,
        company_visible: bool,
    ) -> None:
        writes: list[AuthzTuple] = [
            wiki_page_owner_tuple(page.wiki_page_id, owner_user_id),
            wiki_page_company_link(page.wiki_page_id, page.company_id),
        ]
        if page.parent_page_id is not None:
            writes.append(wiki_page_parent_tuple(page.wiki_page_id, page.parent_page_id))
        if company_visible:
            writes.append(
                wiki_page_company_viewer_tuple(page.wiki_page_id, page.company_id)
            )
        await self._authz.write(writes)

    async def sync_page_moved(
        self,
        wiki_page_id: str,
        *,
        old_parent_page_id: str | None,
        new_parent_page_id: str | None,
    ) -> None:
        if old_parent_page_id == new_parent_page_id:
            return
        writes: list[AuthzTuple] = []
        deletes: list[AuthzTuple] = []
        if new_parent_page_id is not None:
            writes.append(wiki_page_parent_tuple(wiki_page_id, new_parent_page_id))
        if old_parent_page_id is not None:
            deletes.append(wiki_page_parent_tuple(wiki_page_id, old_parent_page_id))
        if writes or deletes:
            await self._authz.write_and_delete(writes, deletes)

    async def sync_page_deleted(self, wiki_page_id: str) -> None:
        deletes = await self._authz.list_tuples(self._obj(wiki_page_id))
        if deletes:
            await self._authz.delete(deletes)

    async def sync_pages_deleted(self, wiki_page_ids: list[str]) -> None:
        for wiki_page_id in wiki_page_ids:
            await self.sync_page_deleted(wiki_page_id)

    async def set_company_visible(
        self,
        wiki_page_id: str,
        company_id: str,
        *,
        company_visible: bool,
    ) -> None:
        link = wiki_page_company_link(wiki_page_id, company_id)
        viewer = wiki_page_company_viewer_tuple(wiki_page_id, company_id)
        if company_visible:
            await self._authz.write([link, viewer])
        else:
            await self._authz.write_and_delete([link], [viewer])

    async def page_is_company_visible(self, wiki_page_id: str, company_id: str) -> bool:
        tuples = await self._authz.list_tuples(self._obj(wiki_page_id))
        company_members = AuthzSubject.company_member(company_id)
        return any(
            item.relation is AuthzRelation.COMPANY_VIEWER
            and item.subject == company_members
            for item in tuples
        )

    async def resolve_owner_user_id(self, wiki_page_id: str) -> str:
        subjects = await self._authz.list_users(
            self._obj(wiki_page_id),
            AuthzRelation.OWNER,
        )
        for subject in subjects:
            if subject.kind is AuthzSubjectKind.USER:
                return subject.value
        raise ValueError(f"wiki page {wiki_page_id} has no FGA owner")

    async def filter_viewable_page_ids(
        self, wiki_page_ids: list[str], *, user_id: str
    ) -> list[str]:
        if not wiki_page_ids:
            return []
        checks = await self._authz.batch_check(
            [
                AuthzCheckItem(
                    subject=AuthzSubject.user(user_id),
                    relation=AuthzRelation.CAN_VIEW,
                    obj=self._obj(wiki_page_id),
                    correlation_id=wiki_page_id,
                )
                for wiki_page_id in wiki_page_ids
            ]
        )
        return [
            wiki_page_id
            for wiki_page_id, allowed in zip(wiki_page_ids, checks, strict=True)
            if allowed
        ]

    async def list_member_items(self, wiki_page_id: str) -> list[WikiPageMember]:
        """Прямые `viewer`/`editor` tuples страницы — без TTU/owner-union, который даёт `list_users`."""
        now = datetime.now(timezone.utc)
        items: list[WikiPageMember] = []
        for relation in _MEMBER_RELATIONS:
            tuples = await self._authz.list_tuples(self._obj(wiki_page_id), relation=relation)
            for item in tuples:
                if item.subject.kind is not AuthzSubjectKind.USER:
                    continue
                items.append(
                    WikiPageMember(
                        wiki_page_id=wiki_page_id,
                        user_id=item.subject.value,
                        relation=_relation_wire(relation),
                        created_at=now,
                    )
                )
        return items

    async def add_member(
        self,
        wiki_page_id: str,
        *,
        user_id: str,
        relation: WikiAccessMemberRelation,
    ) -> None:
        await self._authz.write(
            [wiki_page_member_tuple(wiki_page_id, user_id, _relation_authz(relation))]
        )

    async def remove_member(self, wiki_page_id: str, *, user_id: str) -> None:
        deletes = [
            wiki_page_member_tuple(wiki_page_id, user_id, relation)
            for relation in _MEMBER_RELATIONS
        ]
        await self._authz.delete(deletes)

    async def clear_members(self, wiki_page_id: str) -> None:
        existing = await self.list_member_items(wiki_page_id)
        if not existing:
            return
        deletes = [
            wiki_page_member_tuple(wiki_page_id, item.user_id, _relation_authz(item.relation))
            for item in existing
        ]
        await self._authz.delete(deletes)

    async def replace_members(
        self,
        wiki_page_id: str,
        *,
        members: list[tuple[str, WikiAccessMemberRelation]],
        company_visible: bool,
    ) -> None:
        if company_visible and members:
            raise ValueError("members are forbidden when company_visible=true")
        await self.clear_members(wiki_page_id)
        if not members:
            return
        await self._authz.write(
            [
                wiki_page_member_tuple(wiki_page_id, user_id, _relation_authz(relation))
                for user_id, relation in members
            ]
        )

    async def build_access(
        self,
        page: WikiPage,
        *,
        inherited_from_page_id: str | None,
    ) -> WikiPageAccess:
        members = await self.list_member_items(page.wiki_page_id)
        return WikiPageAccess(
            wiki_page_id=page.wiki_page_id,
            company_visible=page.company_visible,
            inherited_from_page_id=inherited_from_page_id,
            members=members,
            link_enabled=page.link_enabled,
            link_permission=page.link_permission,
        )

    async def inherited_restriction_root(
        self,
        wiki_page_id: str,
        *,
        parents: dict[str, str | None],
        company_visible_by_id: dict[str, bool],
    ) -> str | None:
        """Ближайший предок (включая себя) с company_visible=false — только для UI."""
        current: str | None = wiki_page_id
        seen: set[str] = set()
        while current is not None:
            if current in seen:
                raise ValueError(f"Cycle in wiki tree at page {current}")
            seen.add(current)
            if company_visible_by_id.get(current) is False:
                return current
            current = parents.get(current)
        return None
