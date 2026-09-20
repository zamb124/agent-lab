"""Namespaces RAG: тонкая REST-обвязка тех же `op_*`."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.rag.models import NamespaceCreateRequest, NamespaceDeleteResponse
from apps.rag.realtime.operations import (
    RagNamespaceCreatePayload,
    RagNamespaceDeletePayload,
    RagNamespacesListPayload,
    op_namespaces_create,
    op_namespaces_list,
    op_namespaces_remove,
)
from core.context import require_context
from core.models.identity_models import Namespace
from core.pagination import OffsetPage

from ..dependencies import ContainerDep

router = APIRouter(tags=["namespaces"])


@router.get("/namespaces", response_model=OffsetPage[Namespace])
async def list_namespaces(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[Namespace]:
    return await op_namespaces_list(
        RagNamespacesListPayload(limit=limit, offset=offset),
        user=require_context().user,
        container=container,
    )


@router.post("/namespaces", response_model=Namespace, status_code=201)
async def create_namespace(
    request: NamespaceCreateRequest,
    container: ContainerDep,
    provider: Annotated[str | None, Query()] = None,
) -> Namespace:
    return await op_namespaces_create(
        RagNamespaceCreatePayload(
            name=request.name, description=request.description, provider=provider
        ),
        user=require_context().user,
        container=container,
    )


@router.delete("/namespaces/{namespace_id}", response_model=NamespaceDeleteResponse)
async def delete_namespace(
    namespace_id: str,
    container: ContainerDep,
    provider: Annotated[str | None, Query()] = None,
) -> NamespaceDeleteResponse:
    return await op_namespaces_remove(
        RagNamespaceDeletePayload(name=namespace_id, provider=provider),
        user=require_context().user,
        container=container,
    )
