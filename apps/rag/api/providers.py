"""Провайдеры RAG: тонкая REST-обвязка того же `op_providers_list`."""

from fastapi import APIRouter

from apps.rag.models import ProvidersView
from apps.rag.realtime.operations import RagEmptyPayload, op_providers_list
from core.context import require_context

from ..dependencies import ContainerDep

router = APIRouter(tags=["providers"])


@router.get("/providers", response_model=ProvidersView)
async def list_providers(container: ContainerDep) -> ProvidersView:
    return await op_providers_list(
        RagEmptyPayload(), user=require_context().user, container=container
    )
