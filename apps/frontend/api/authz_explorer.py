"""REST-зеркало команд `frontend/authz_explorer/*`."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.frontend.di import Di
from apps.frontend.realtime.authz_explorer_operations import (
    AuthzExplorerByObjectPayload,
    AuthzExplorerByUserPayload,
    AuthzExplorerObjectsPayload,
    AuthzExplorerWhyPayload,
    op_authz_explorer_by_object,
    op_authz_explorer_by_user,
    op_authz_explorer_objects,
    op_authz_explorer_revoke,
    op_authz_explorer_why,
)
from core.authz.explorer import (
    AuthzExplorerByObjectResponse,
    AuthzExplorerByUserResponse,
    AuthzExplorerObjectsResponse,
    AuthzExplorerRevokeRequest,
    AuthzExplorerRevokeResponse,
    AuthzExplorerWhyResponse,
)
from core.authz.types import AuthzObjectType
from core.context import require_context

router = APIRouter(prefix="/api/authz/explorer", tags=["authz-explorer"])


@router.get("/by-user", response_model=AuthzExplorerByUserResponse)
async def explorer_by_user(
    di: Di,
    user_id: Annotated[str, Query(min_length=1)],
) -> AuthzExplorerByUserResponse:
    return await op_authz_explorer_by_user(
        AuthzExplorerByUserPayload(user_id=user_id), user=require_context().user, di=di
    )


@router.get("/by-object", response_model=AuthzExplorerByObjectResponse)
async def explorer_by_object(
    di: Di,
    object_type: AuthzObjectType,
    object_key: Annotated[str, Query(min_length=1)],
) -> AuthzExplorerByObjectResponse:
    return await op_authz_explorer_by_object(
        AuthzExplorerByObjectPayload(object_type=object_type, object_key=object_key),
        user=require_context().user,
        di=di,
    )


@router.get("/why", response_model=AuthzExplorerWhyResponse)
async def explorer_why(
    di: Di,
    user_id: Annotated[str, Query(min_length=1)],
    object_type: AuthzObjectType,
    object_key: Annotated[str, Query(min_length=1)],
) -> AuthzExplorerWhyResponse:
    return await op_authz_explorer_why(
        AuthzExplorerWhyPayload(user_id=user_id, object_type=object_type, object_key=object_key),
        user=require_context().user,
        di=di,
    )


@router.get("/objects", response_model=AuthzExplorerObjectsResponse)
async def explorer_objects(
    di: Di,
    q: Annotated[str, Query()] = "",
    object_type: AuthzObjectType | None = None,
) -> AuthzExplorerObjectsResponse:
    return await op_authz_explorer_objects(
        AuthzExplorerObjectsPayload(q=q, object_type=object_type),
        user=require_context().user,
        di=di,
    )


@router.post("/revoke", response_model=AuthzExplorerRevokeResponse)
async def explorer_revoke(request_body: AuthzExplorerRevokeRequest, di: Di) -> AuthzExplorerRevokeResponse:
    return await op_authz_explorer_revoke(request_body, user=require_context().user, di=di)
