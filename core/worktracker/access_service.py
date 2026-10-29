"""Work queue access: OpenFGA sole PDP."""

from __future__ import annotations

from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.service import AuthzService
from core.authz.types import AuthzObjectType, AuthzRelation, AuthzSubjectKind
from core.worktracker.authz_tuples import (
    work_queue_company_link,
    work_queue_member_tuple,
    work_queue_owner_tuple,
)
from core.worktracker.queue_access import WorkQueueMemberRelation

_QUEUE_RELATIONS: tuple[AuthzRelation, ...] = (
    AuthzRelation.OWNER,
    AuthzRelation.MEMBER,
)


def _relation_authz(relation: WorkQueueMemberRelation) -> AuthzRelation:
    if relation == "owner":
        return AuthzRelation.OWNER
    return AuthzRelation.MEMBER


def _relation_wire(relation: AuthzRelation) -> WorkQueueMemberRelation:
    if relation is AuthzRelation.OWNER:
        return "owner"
    if relation is AuthzRelation.MEMBER:
        return "member"
    raise ValueError(f"unsupported work_queue relation: {relation}")


class WorkQueueAccessService:
    def __init__(self, authz: AuthzService) -> None:
        self._authz: AuthzService = authz

    def _obj(self, work_queue_id: str) -> AuthzObject:
        return AuthzObject.work_queue(work_queue_id)

    async def resolve_company_admin_owner(self, company_id: str) -> str:
        """Stable owner for queue create when explicit creator is absent."""
        subjects = await self._authz.list_users(
            AuthzObject.company(company_id),
            AuthzRelation.CAN_ADMIN,
        )
        user_ids = sorted(
            {
                subject.value.strip()
                for subject in subjects
                if subject.kind is AuthzSubjectKind.USER and subject.value.strip() != ""
            }
        )
        if not user_ids:
            raise ValueError(
                f"work queue owner: no company CAN_ADMIN for {company_id!r}"
            )
        return user_ids[0]

    async def sync_queue_created(
        self,
        work_queue_id: str,
        *,
        company_id: str,
        owner_user_id: str,
    ) -> None:
        writes: list[AuthzTuple] = [
            work_queue_company_link(work_queue_id, company_id),
            work_queue_owner_tuple(work_queue_id, owner_user_id),
        ]
        await self._authz.write(writes)

    async def set_member(
        self,
        work_queue_id: str,
        *,
        user_id: str,
        relation: WorkQueueMemberRelation,
    ) -> None:
        target = _relation_authz(relation)
        deletes = [
            work_queue_member_tuple(work_queue_id, user_id, item)
            for item in _QUEUE_RELATIONS
            if item is not target
        ]
        write = work_queue_member_tuple(work_queue_id, user_id, target)
        await self._authz.write_and_delete([write], deletes)

    async def remove_member(self, work_queue_id: str, *, user_id: str) -> None:
        deletes = [
            work_queue_member_tuple(work_queue_id, user_id, item) for item in _QUEUE_RELATIONS
        ]
        await self._authz.delete(deletes)

    async def sync_queue_deleted(self, work_queue_id: str) -> None:
        deletes = await self._authz.list_tuples(self._obj(work_queue_id))
        if deletes:
            await self._authz.delete(deletes)

    async def list_member_rows_by_user_id_asc(
        self, work_queue_id: str
    ) -> list[tuple[str, WorkQueueMemberRelation]]:
        items: list[tuple[str, WorkQueueMemberRelation]] = []
        for relation in _QUEUE_RELATIONS:
            tuples = await self._authz.list_tuples(self._obj(work_queue_id), relation=relation)
            for item in tuples:
                if item.subject.kind is not AuthzSubjectKind.USER:
                    continue
                items.append((item.subject.value, _relation_wire(relation)))
        items.sort(key=lambda row: row[0])
        return items

    async def list_viewable_queue_ids(self, *, user_id: str) -> list[str]:
        objects = await self._authz.list_objects(
            AuthzSubject.user(user_id),
            AuthzRelation.CAN_VIEW,
            AuthzObjectType.WORK_QUEUE,
        )
        return [obj.object_key for obj in objects]
