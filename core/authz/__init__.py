"""Единый authorization фасад платформы (OpenFGA).

Apps импортируют только публичные символы из этого пакета.
Прямой `openfga_sdk` / `OpenFgaClient` вне `core/authz` запрещён.
"""

from core.authz.company_sync import (
    check_company_admin,
    company_role_tuples,
    company_roles_imply_admin,
    remove_company_member,
    require_company_admin,
    sync_company_member_roles,
)
from core.authz.errors import AuthzDenied, AuthzError, AuthzUnavailable
from core.authz.group_sync import group_member_tuple, remove_user_groups, sync_user_groups
from core.authz.models import (
    AuthzCheckItem,
    AuthzExpandTree,
    AuthzObject,
    AuthzSubject,
    AuthzTuple,
)
from core.authz.service import AuthzService
from core.authz.types import AuthzConsistency, AuthzObjectType, AuthzRelation, AuthzSubjectKind

__all__ = [
    "AuthzCheckItem",
    "AuthzConsistency",
    "AuthzDenied",
    "AuthzError",
    "AuthzExpandTree",
    "AuthzObject",
    "AuthzObjectType",
    "AuthzRelation",
    "AuthzService",
    "AuthzSubject",
    "AuthzSubjectKind",
    "AuthzTuple",
    "AuthzUnavailable",
    "check_company_admin",
    "company_role_tuples",
    "company_roles_imply_admin",
    "group_member_tuple",
    "remove_company_member",
    "remove_user_groups",
    "require_company_admin",
    "sync_company_member_roles",
    "sync_user_groups",
]
