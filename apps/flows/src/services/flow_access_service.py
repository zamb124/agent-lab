"""Flow / branch / tool access: OpenFGA tuple dual-write + list filters."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from apps.flows.authz.tuples import (
    flow_branch_company_viewer_tuple,
    flow_branch_flow_link,
    flow_branch_group_viewer_tuple,
    flow_company_link,
    flow_company_viewer_tuple,
    flow_group_viewer_tuple,
    flow_owner_tuple,
    flow_platform_link,
    flow_ui_share_flow_link,
    flow_ui_share_owner_tuple,
    flow_ui_share_public_editor_tuple,
    flow_ui_share_public_viewer_tuple,
    tool_company_link,
    tool_company_viewer_tuple,
    tool_group_viewer_tuple,
    tool_platform_link,
)
from apps.flows.src.models.flow_config import FlowConfig
from core.authz.models import AuthzCheckItem, AuthzObject, AuthzSubject, AuthzTuple
from core.authz.service import AuthzService
from core.authz.types import AuthzObjectType, AuthzRelation


class FlowAccessService:
    def __init__(self, authz: AuthzService) -> None:
        self._authz: AuthzService = authz

    async def filter_viewable_flow_ids(
        self, flow_ids: Sequence[str], *, user_id: str
    ) -> list[str]:
        return await self._filter_viewable_ids(
            flow_ids, user_id=user_id, obj_factory=AuthzObject.flow
        )

    async def page_viewable_flow_ids(
        self,
        flow_ids: Sequence[str],
        *,
        user_id: str,
        offset: int,
        limit: int,
    ) -> list[str]:
        """Viewable ids in catalog order for one OffsetPage.

        Walks ``flow_ids`` and ``batch_check``s windows until ``offset+limit``
        viewable ids (or the catalog ends). Does not Check the remainder of a
        large company catalog on every list request. Sole PDP remains OpenFGA
        Check (TTU ``admin from platform`` included); ListObjects is not used.
        """
        if not flow_ids or limit <= 0:
            return []
        if offset < 0:
            raise ValueError("offset must be >= 0")
        needed = offset + limit
        viewable: list[str] = []
        pos = 0
        while pos < len(flow_ids) and len(viewable) < needed:
            remaining = needed - len(viewable)
            window = flow_ids[pos : pos + remaining]
            pos += len(window)
            allowed = await self.filter_viewable_flow_ids(window, user_id=user_id)
            viewable.extend(allowed)
        return viewable[offset : offset + limit]

    async def filter_viewable_tool_ids(
        self, tool_ids: Sequence[str], *, user_id: str
    ) -> list[str]:
        return await self._filter_viewable_ids(
            tool_ids, user_id=user_id, obj_factory=AuthzObject.tool
        )

    async def list_viewable_flow_ids(self, *, user_id: str) -> list[str]:
        objects = await self._authz.list_objects(
            AuthzSubject.user(user_id),
            AuthzRelation.CAN_VIEW,
            AuthzObjectType.FLOW,
        )
        return [obj.object_key for obj in objects]

    async def list_viewable_tool_ids(self, *, user_id: str) -> list[str]:
        objects = await self._authz.list_objects(
            AuthzSubject.user(user_id),
            AuthzRelation.CAN_VIEW,
            AuthzObjectType.TOOL,
        )
        return [obj.object_key for obj in objects]

    async def _filter_viewable_ids(
        self,
        object_ids: Sequence[str],
        *,
        user_id: str,
        obj_factory: Callable[[str], AuthzObject],
    ) -> list[str]:
        if not object_ids:
            return []
        allowed = await self._authz.batch_check(
            [
                AuthzCheckItem(
                    subject=AuthzSubject.user(user_id),
                    relation=AuthzRelation.CAN_VIEW,
                    obj=obj_factory(object_id),
                    correlation_id=object_id,
                )
                for object_id in object_ids
            ]
        )
        return [
            object_id
            for object_id, ok in zip(object_ids, allowed, strict=True)
            if ok
        ]

    def _permission_viewer_writes(
        self,
        *,
        flow_id: str,
        company_id: str,
        permission: Sequence[str],
    ) -> list[AuthzTuple]:
        groups = [item.strip() for item in permission if item.strip()]
        if not groups:
            return [flow_company_viewer_tuple(flow_id, company_id)]
        return [
            flow_group_viewer_tuple(flow_id, group_name, company_id=company_id)
            for group_name in groups
        ]

    def _branch_permission_viewer_writes(
        self,
        *,
        flow_id: str,
        branch_id: str,
        company_id: str,
        permission: Sequence[str],
        inherit_flow: bool,
    ) -> list[AuthzTuple]:
        if inherit_flow:
            return []
        groups = [item.strip() for item in permission if item.strip()]
        if not groups:
            return [flow_branch_company_viewer_tuple(flow_id, branch_id, company_id)]
        return [
            flow_branch_group_viewer_tuple(
                flow_id, branch_id, group_name, company_id=company_id
            )
            for group_name in groups
        ]

    async def sync_flow_saved(
        self,
        config: FlowConfig,
        *,
        company_id: str,
        owner_user_id: str,
    ) -> None:
        flow_id = config.flow_id
        existing = await self._authz.list_tuples(AuthzObject.flow(flow_id))
        writes: list[AuthzTuple] = [
            flow_company_link(flow_id, company_id),
            flow_platform_link(flow_id),
            flow_owner_tuple(flow_id, owner_user_id),
            *self._permission_viewer_writes(
                flow_id=flow_id,
                company_id=company_id,
                permission=config.permission,
            ),
        ]
        desired_set = frozenset(writes)
        existing_set = frozenset(existing)
        await self._authz.write_and_delete(
            list(desired_set - existing_set),
            list(existing_set - desired_set),
        )
        branch_writes: list[AuthzTuple] = []
        branch_deletes: list[AuthzTuple] = []
        for branch_id, branch in config.branches.items():
            branch_obj = AuthzObject.flow_branch(flow_id, branch_id)
            branch_existing = await self._authz.list_tuples(branch_obj)
            inherit = not branch.permission
            branch_desired: list[AuthzTuple] = [flow_branch_flow_link(flow_id, branch_id)]
            branch_desired.extend(
                self._branch_permission_viewer_writes(
                    flow_id=flow_id,
                    branch_id=branch_id,
                    company_id=company_id,
                    permission=branch.permission,
                    inherit_flow=inherit,
                )
            )
            branch_desired_set = frozenset(branch_desired)
            branch_existing_set = frozenset(branch_existing)
            branch_writes.extend(branch_desired_set - branch_existing_set)
            branch_deletes.extend(branch_existing_set - branch_desired_set)
        if branch_writes or branch_deletes:
            await self._authz.write_and_delete(branch_writes, branch_deletes)

    async def sync_flow_deleted(self, flow_id: str, *, branch_ids: Sequence[str]) -> None:
        deletes = await self._authz.list_tuples(AuthzObject.flow(flow_id))
        for branch_id in branch_ids:
            deletes.extend(
                await self._authz.list_tuples(AuthzObject.flow_branch(flow_id, branch_id))
            )
        if deletes:
            await self._authz.delete(deletes)

    async def sync_branch_deleted(self, flow_id: str, branch_id: str) -> None:
        deletes = await self._authz.list_tuples(AuthzObject.flow_branch(flow_id, branch_id))
        if deletes:
            await self._authz.delete(deletes)

    async def sync_tool_saved(
        self,
        tool_id: str,
        *,
        company_id: str,
        permission: Sequence[str],
    ) -> None:
        existing = await self._authz.list_tuples(AuthzObject.tool(tool_id))
        groups = [item.strip() for item in permission if item.strip()]
        desired: list[AuthzTuple] = [
            tool_company_link(tool_id, company_id),
            tool_platform_link(tool_id),
        ]
        if not groups:
            desired.append(tool_company_viewer_tuple(tool_id, company_id))
        else:
            desired.extend(
                tool_group_viewer_tuple(tool_id, group_name, company_id=company_id)
                for group_name in groups
            )
        desired_set = frozenset(desired)
        existing_set = frozenset(existing)
        writes = list(desired_set - existing_set)
        deletes = list(existing_set - desired_set)
        await self._authz.write_and_delete(writes, deletes)

    async def sync_tool_deleted(self, tool_id: str) -> None:
        deletes = await self._authz.list_tuples(AuthzObject.tool(tool_id))
        if deletes:
            await self._authz.delete(deletes)

    async def sync_share_created(
        self,
        *,
        share_grant_id: str,
        flow_id: str,
        owner_user_id: str,
        permission: str,
    ) -> None:
        writes: list[AuthzTuple] = [
            flow_ui_share_flow_link(share_grant_id, flow_id),
            flow_ui_share_owner_tuple(share_grant_id, owner_user_id),
        ]
        if permission == "editor":
            writes.append(flow_ui_share_public_editor_tuple(share_grant_id))
        elif permission == "viewer":
            writes.append(flow_ui_share_public_viewer_tuple(share_grant_id))
        else:
            raise ValueError(f"unsupported flow_ui_share permission: {permission}")
        await self._authz.write(writes)

    async def sync_share_revoked(self, share_grant_id: str) -> None:
        deletes = await self._authz.list_tuples(AuthzObject.flow_ui_share(share_grant_id))
        if deletes:
            await self._authz.delete(deletes)
