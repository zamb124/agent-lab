"""Sync channel access: OpenFGA sole PDP."""

from __future__ import annotations

from apps.sync.authz.tuples import sync_channel_company_link, sync_channel_member_tuple
from apps.sync.models.channels import ChannelMemberRole
from core.authz.models import AuthzObject, AuthzTuple
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation, AuthzSubjectKind

_CHANNEL_MEMBER_RELATIONS: tuple[AuthzRelation, ...] = (
    AuthzRelation.OWNER,
    AuthzRelation.ADMIN,
    AuthzRelation.MEMBER,
)


def _role_relation(role: ChannelMemberRole) -> AuthzRelation:
    if role == "owner":
        return AuthzRelation.OWNER
    if role == "admin":
        return AuthzRelation.ADMIN
    return AuthzRelation.MEMBER


def _relation_role(relation: AuthzRelation) -> ChannelMemberRole:
    if relation is AuthzRelation.OWNER:
        return "owner"
    if relation is AuthzRelation.ADMIN:
        return "admin"
    if relation is AuthzRelation.MEMBER:
        return "member"
    raise ValueError(f"unsupported sync channel relation: {relation}")


class SyncChannelAccessService:
    def __init__(self, authz: AuthzService) -> None:
        self._authz: AuthzService = authz

    def _obj(self, channel_id: str) -> AuthzObject:
        return AuthzObject.sync_channel(channel_id)

    async def sync_channel_created(
        self,
        channel_id: str,
        *,
        company_id: str,
        owner_user_id: str,
        member_user_ids: list[str],
    ) -> None:
        writes: list[AuthzTuple] = [
            sync_channel_company_link(channel_id, company_id),
            sync_channel_member_tuple(channel_id, owner_user_id, AuthzRelation.OWNER),
        ]
        for user_id in member_user_ids:
            if user_id == owner_user_id:
                continue
            writes.append(
                sync_channel_member_tuple(channel_id, user_id, AuthzRelation.MEMBER)
            )
        await self._authz.write(writes)

    async def set_member(
        self,
        channel_id: str,
        *,
        user_id: str,
        relation: ChannelMemberRole,
    ) -> None:
        target = _role_relation(relation)
        deletes = [
            sync_channel_member_tuple(channel_id, user_id, item)
            for item in _CHANNEL_MEMBER_RELATIONS
            if item is not target
        ]
        write = sync_channel_member_tuple(channel_id, user_id, target)
        await self._authz.write_and_delete([write], deletes)

    async def remove_member(self, channel_id: str, *, user_id: str) -> None:
        deletes = [
            sync_channel_member_tuple(channel_id, user_id, item)
            for item in _CHANNEL_MEMBER_RELATIONS
        ]
        await self._authz.delete(deletes)

    async def sync_channel_deleted(self, channel_id: str) -> None:
        deletes = await self._authz.list_tuples(self._obj(channel_id))
        if deletes:
            await self._authz.delete(deletes)

    async def list_member_rows(self, channel_id: str) -> list[tuple[str, ChannelMemberRole]]:
        items: list[tuple[str, ChannelMemberRole]] = []
        for relation in _CHANNEL_MEMBER_RELATIONS:
            tuples = await self._authz.list_tuples(self._obj(channel_id), relation=relation)
            for item in tuples:
                if item.subject.kind is not AuthzSubjectKind.USER:
                    continue
                items.append((item.subject.value, _relation_role(relation)))
        items.sort(key=lambda row: row[0])
        return items

    async def list_member_user_ids(self, channel_id: str) -> list[str]:
        """FGA membership (owner|admin|member) — sole source for recipients/lists."""
        user_ids: set[str] = set()
        for relation in _CHANNEL_MEMBER_RELATIONS:
            subjects = await self._authz.list_users(self._obj(channel_id), relation)
            for subject in subjects:
                if subject.kind is not AuthzSubjectKind.USER:
                    continue
                user_ids.add(subject.value)
        return sorted(user_ids)
