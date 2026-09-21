"""REST-зеркало команд `frontend/namespaces/*` (консоль admin)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from apps.frontend.dependencies import ContainerDep
from apps.frontend.realtime.namespace_operations import (
    CONSOLE_NAMESPACE_KINDS,
    ConsoleNamespaceCreatePayload,
    ConsoleNamespacesListPayload,
    op_namespaces_console_create,
    op_namespaces_console_list,
    op_namespaces_personal,
)
from core.context import require_context
from core.models.identity_models import Namespace, NamespaceKind
from core.pagination import OffsetPage
from core.websocket import EmptyPayload

router = APIRouter(prefix="/api/namespaces", tags=["namespaces"])


@router.get("", response_model=OffsetPage[Namespace])
async def list_console_namespaces(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
    kind: Annotated[Literal["company_workspace", "personal", "all"], Query()] = "all",
) -> OffsetPage[Namespace]:
    kinds = CONSOLE_NAMESPACE_KINDS if kind == "all" else frozenset({NamespaceKind(kind)})
    return await op_namespaces_console_list(
        ConsoleNamespacesListPayload(limit=limit, offset=offset, kinds=kinds),
        user=require_context().user,
        container=container,
    )


@router.post("", response_model=Namespace, status_code=201)
async def create_console_namespace(body: ConsoleNamespaceCreatePayload, container: ContainerDep) -> Namespace:
    return await op_namespaces_console_create(body, user=require_context().user, container=container)


@router.get("/me/personal", response_model=Namespace)
async def get_my_personal_namespace(container: ContainerDep) -> Namespace:
    return await op_namespaces_personal(
        EmptyPayload(), user=require_context().user, container=container
    )
