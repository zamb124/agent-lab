"""Команды Access Explorer: явные гранты компании через AuthzService (company admin)."""

from __future__ import annotations

from pydantic import Field

from apps.frontend.di import Di
from core.authz.explorer import (
    AuthzExplorerByObjectResponse,
    AuthzExplorerByUserResponse,
    AuthzExplorerObjectsResponse,
    AuthzExplorerRevokeRequest,
    AuthzExplorerRevokeResponse,
    AuthzExplorerWhyResponse,
)
from core.authz.types import AuthzObjectType
from core.models import StrictBaseModel
from core.models.identity_models import User
from core.request_scope import require_company_admin


class AuthzExplorerByUserPayload(StrictBaseModel):
    user_id: str = Field(min_length=1)


class AuthzExplorerByObjectPayload(StrictBaseModel):
    object_type: AuthzObjectType
    object_key: str = Field(min_length=1)


class AuthzExplorerWhyPayload(AuthzExplorerByObjectPayload):
    user_id: str = Field(min_length=1)


class AuthzExplorerObjectsPayload(StrictBaseModel):
    q: str = ""
    object_type: AuthzObjectType | None = None


async def op_authz_explorer_by_user(
    payload: AuthzExplorerByUserPayload, *, user: User, di: Di
) -> AuthzExplorerByUserResponse:
    _ = user
    scope = await require_company_admin(di.authz_service)
    return await di.authz_explorer_service.by_user(user_id=payload.user_id, company_id=scope.company_id)


async def op_authz_explorer_by_object(
    payload: AuthzExplorerByObjectPayload, *, user: User, di: Di
) -> AuthzExplorerByObjectResponse:
    _ = user
    scope = await require_company_admin(di.authz_service)
    return await di.authz_explorer_service.by_object(
        object_type=AuthzObjectType(payload.object_type), object_key=payload.object_key, company_id=scope.company_id
    )


async def op_authz_explorer_why(
    payload: AuthzExplorerWhyPayload, *, user: User, di: Di
) -> AuthzExplorerWhyResponse:
    _ = user
    scope = await require_company_admin(di.authz_service)
    return await di.authz_explorer_service.why(
        user_id=payload.user_id,
        object_type=AuthzObjectType(payload.object_type),
        object_key=payload.object_key,
        company_id=scope.company_id,
    )


async def op_authz_explorer_objects(
    payload: AuthzExplorerObjectsPayload, *, user: User, di: Di
) -> AuthzExplorerObjectsResponse:
    _ = user
    scope = await require_company_admin(di.authz_service)
    items = await di.authz_explorer_service.search_objects(
        company_id=scope.company_id,
        query=payload.q,
        object_type=AuthzObjectType(payload.object_type) if payload.object_type is not None else None,
    )
    return AuthzExplorerObjectsResponse(items=items)


async def op_authz_explorer_revoke(
    payload: AuthzExplorerRevokeRequest, *, user: User, di: Di
) -> AuthzExplorerRevokeResponse:
    _ = user
    scope = await require_company_admin(di.authz_service)
    return await di.authz_explorer_service.revoke(payload, company_id=scope.company_id)
