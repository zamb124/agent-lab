"""Контракт Access Explorer: явные гранты для company admin, не сырой FGA UI."""

from enum import StrEnum

from pydantic import Field

from core.authz.types import AuthzObjectType, AuthzRelation, AuthzSubjectKind
from core.models.base import StrictBaseModel


class AuthzGrantSource(StrEnum):
    DIRECT = "direct"
    GROUP = "group"
    INHERITED = "inherited"
    COMPANY_VISIBLE = "company_visible"


class AuthzTitleStatus(StrEnum):
    LOADED = "loaded"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"


class AuthzWhyReason(StrEnum):
    DIRECT_GRANT = "direct_grant"
    GROUP_MEMBERSHIP = "group_membership"
    PARENT_INHERIT = "parent_inherit"
    COMPANY_VISIBLE = "company_visible"


class AuthzGrantRow(StrictBaseModel):
    subject_kind: AuthzSubjectKind
    subject_id: str
    relation: AuthzRelation
    object_type: AuthzObjectType
    object_key: str
    title: str | None
    title_status: AuthzTitleStatus
    href: str
    manage_href: str
    grant_source: AuthzGrantSource
    namespace: str | None
    can_revoke: bool
    why_reasons: list[AuthzWhyReason] = Field(default_factory=list)


class AuthzExplorerSummary(StrictBaseModel):
    explicit_grant_count: int
    company_visible: bool
    group_count: int
    counts_by_type: dict[str, int]
    counts_by_relation: dict[str, int]


class AuthzExplorerByUserResponse(StrictBaseModel):
    user_id: str
    company_visible: bool
    items: list[AuthzGrantRow]
    summary: AuthzExplorerSummary


class AuthzExplorerByObjectResponse(StrictBaseModel):
    object_type: AuthzObjectType
    object_key: str
    title: str | None
    title_status: AuthzTitleStatus
    href: str
    manage_href: str
    namespace: str | None
    company_visible: bool
    items: list[AuthzGrantRow]
    summary: AuthzExplorerSummary


class AuthzExplorerWhyResponse(StrictBaseModel):
    user_id: str
    object_type: AuthzObjectType
    object_key: str
    allowed: bool
    reasons: list[AuthzWhyReason]


class AuthzExplorerObjectHit(StrictBaseModel):
    object_type: AuthzObjectType
    object_key: str
    title: str | None
    title_status: AuthzTitleStatus
    href: str
    namespace: str | None


class AuthzExplorerObjectsResponse(StrictBaseModel):
    items: list[AuthzExplorerObjectHit]


class AuthzExplorerRevokeRequest(StrictBaseModel):
    object_type: AuthzObjectType
    object_key: str
    relation: AuthzRelation
    subject_kind: AuthzSubjectKind
    subject_id: str


class AuthzExplorerRevokeResponse(StrictBaseModel):
    revoked: bool
