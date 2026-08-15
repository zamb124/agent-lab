"""Access Explorer API — company admin, явные гранты через AuthzService."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.frontend.dependencies import ContainerDep, require_frontend_user
from core.authz.explorer import (
    AuthzExplorerByObjectResponse,
    AuthzExplorerByUserResponse,
    AuthzExplorerObjectsResponse,
    AuthzExplorerRevokeRequest,
    AuthzExplorerRevokeResponse,
    AuthzExplorerWhyResponse,
)
from core.authz.types import AuthzObjectType
from core.context import require_active_company

router = APIRouter(prefix="/api/authz/explorer", tags=["authz-explorer"])


async def _require_explorer_admin(container: ContainerDep) -> tuple[str, str]:
    user = require_frontend_user()
    company = require_active_company()
    await container.authz_service.require_company_admin(
        company_id=company.company_id,
        user_id=user.user_id,
    )
    return company.company_id, user.user_id


@router.get("/by-user", response_model=AuthzExplorerByUserResponse)
async def explorer_by_user(
    container: ContainerDep,
    user_id: Annotated[str, Query(min_length=1)],
) -> AuthzExplorerByUserResponse:
    company_id, _actor_user_id = await _require_explorer_admin(container)
    return await container.authz_explorer_service.by_user(
        user_id=user_id,
        company_id=company_id,
    )


@router.get("/by-object", response_model=AuthzExplorerByObjectResponse)
async def explorer_by_object(
    container: ContainerDep,
    object_type: AuthzObjectType,
    object_key: Annotated[str, Query(min_length=1)],
) -> AuthzExplorerByObjectResponse:
    company_id, _actor_user_id = await _require_explorer_admin(container)
    return await container.authz_explorer_service.by_object(
        object_type=object_type,
        object_key=object_key,
        company_id=company_id,
    )


@router.get("/why", response_model=AuthzExplorerWhyResponse)
async def explorer_why(
    container: ContainerDep,
    user_id: Annotated[str, Query(min_length=1)],
    object_type: AuthzObjectType,
    object_key: Annotated[str, Query(min_length=1)],
) -> AuthzExplorerWhyResponse:
    company_id, _actor_user_id = await _require_explorer_admin(container)
    return await container.authz_explorer_service.why(
        user_id=user_id,
        object_type=object_type,
        object_key=object_key,
        company_id=company_id,
    )


@router.get("/objects", response_model=AuthzExplorerObjectsResponse)
async def explorer_objects(
    container: ContainerDep,
    q: Annotated[str, Query()] = "",
    object_type: AuthzObjectType | None = None,
) -> AuthzExplorerObjectsResponse:
    company_id, _actor_user_id = await _require_explorer_admin(container)
    items = await container.authz_explorer_service.search_objects(
        company_id=company_id,
        query=q,
        object_type=object_type,
    )
    return AuthzExplorerObjectsResponse(items=items)


@router.post("/revoke", response_model=AuthzExplorerRevokeResponse)
async def explorer_revoke(
    request: AuthzExplorerRevokeRequest,
    container: ContainerDep,
) -> AuthzExplorerRevokeResponse:
    company_id, _actor_user_id = await _require_explorer_admin(container)
    return await container.authz_explorer_service.revoke(
        request,
        company_id=company_id,
    )
