"""Flows-specific OpenFGA tuple helpers."""

from __future__ import annotations

from core.authz.ids import group_member_company_id
from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.types import AuthzRelation

_VIEWER_EDITOR: frozenset[AuthzRelation] = frozenset(
    {AuthzRelation.VIEWER, AuthzRelation.EDITOR}
)


def flow_company_link(flow_id: str, company_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
        relation=AuthzRelation.COMPANY,
        obj=AuthzObject.flow(flow_id),
    )


def flow_platform_link(flow_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.platform()),
        relation=AuthzRelation.PLATFORM,
        obj=AuthzObject.flow(flow_id),
    )


def flow_owner_tuple(flow_id: str, owner_user_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.user(owner_user_id),
        relation=AuthzRelation.OWNER,
        obj=AuthzObject.flow(flow_id),
    )


def flow_group_viewer_tuple(
    flow_id: str, group_name: str, *, company_id: str
) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.group_member(
            group_name,
            company_id=group_member_company_id(group_name, company_id),
        ),
        relation=AuthzRelation.VIEWER,
        obj=AuthzObject.flow(flow_id),
    )


def flow_company_viewer_tuple(flow_id: str, company_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.company_member(company_id),
        relation=AuthzRelation.VIEWER,
        obj=AuthzObject.flow(flow_id),
    )


def flow_branch_flow_link(flow_id: str, branch_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.flow(flow_id)),
        relation=AuthzRelation.FLOW,
        obj=AuthzObject.flow_branch(flow_id, branch_id),
    )


def flow_branch_group_viewer_tuple(
    flow_id: str, branch_id: str, group_name: str, *, company_id: str
) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.group_member(
            group_name,
            company_id=group_member_company_id(group_name, company_id),
        ),
        relation=AuthzRelation.VIEWER,
        obj=AuthzObject.flow_branch(flow_id, branch_id),
    )


def flow_branch_company_viewer_tuple(
    flow_id: str, branch_id: str, company_id: str
) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.company_member(company_id),
        relation=AuthzRelation.VIEWER,
        obj=AuthzObject.flow_branch(flow_id, branch_id),
    )


def tool_company_link(tool_id: str, company_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
        relation=AuthzRelation.COMPANY,
        obj=AuthzObject.tool(tool_id),
    )


def tool_platform_link(tool_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.platform()),
        relation=AuthzRelation.PLATFORM,
        obj=AuthzObject.tool(tool_id),
    )


def tool_group_viewer_tuple(
    tool_id: str, group_name: str, *, company_id: str
) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.group_member(
            group_name,
            company_id=group_member_company_id(group_name, company_id),
        ),
        relation=AuthzRelation.VIEWER,
        obj=AuthzObject.tool(tool_id),
    )


def tool_company_viewer_tuple(tool_id: str, company_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.company_member(company_id),
        relation=AuthzRelation.VIEWER,
        obj=AuthzObject.tool(tool_id),
    )


def flow_ui_share_flow_link(share_grant_id: str, flow_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.object_ref(AuthzObject.flow(flow_id)),
        relation=AuthzRelation.FLOW,
        obj=AuthzObject.flow_ui_share(share_grant_id),
    )


def flow_ui_share_owner_tuple(share_grant_id: str, owner_user_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.user(owner_user_id),
        relation=AuthzRelation.OWNER,
        obj=AuthzObject.flow_ui_share(share_grant_id),
    )


def flow_ui_share_public_viewer_tuple(share_grant_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.public(),
        relation=AuthzRelation.VIEWER,
        obj=AuthzObject.flow_ui_share(share_grant_id),
    )


def flow_ui_share_public_editor_tuple(share_grant_id: str) -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.public(),
        relation=AuthzRelation.EDITOR,
        obj=AuthzObject.flow_ui_share(share_grant_id),
    )


def assert_viewer_or_editor(relation: AuthzRelation) -> AuthzRelation:
    if relation not in _VIEWER_EDITOR:
        raise ValueError(f"expected viewer|editor, got {relation}")
    return relation
