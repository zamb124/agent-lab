"""Провайдеры RAG: тонкая REST-обвязка того же `op_providers_list`."""

from fastapi import APIRouter

from apps.rag.models import ProvidersView
from apps.rag.realtime.operations import op_providers_list
from core.context import require_context
from core.websocket import EmptyPayload

from ..dependencies import ContainerDep

router = APIRouter(tags=["providers"])


@router.get("/providers", response_model=ProvidersView)
async def list_providers(container: ContainerDep) -> ProvidersView:
    return await op_providers_list(
        EmptyPayload(), user=require_context().user, container=container
    )
