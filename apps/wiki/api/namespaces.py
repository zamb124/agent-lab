"""Список рабочих пространств: тонкая REST-обвязка того же `op_namespaces_list`."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.wiki.dependencies import ContainerDep
from core.context import require_context
from core.models.identity_models import Namespace
from core.namespace.operations import NamespacesListPayload, op_namespaces_list
from core.pagination import OffsetPage

router = APIRouter(prefix="/namespaces", tags=["wiki-namespaces"])


@router.get("", response_model=OffsetPage[Namespace])
async def list_wiki_namespaces(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[Namespace]:
    return await op_namespaces_list(
        NamespacesListPayload(limit=limit, offset=offset),
        user=require_context().user,
        container=container,
    )
