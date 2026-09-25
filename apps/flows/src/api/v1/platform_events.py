"""REST-зеркало каталога platform events для UI триггеров."""

from fastapi import APIRouter

from apps.flows.di import Di
from apps.flows.realtime.trigger_operations import op_flows_platform_events_catalog
from core.context import require_context
from core.events import PlatformEventCatalogResponse
from core.websocket import EmptyPayload

router = APIRouter(tags=["platform-events"])


@router.get("/catalog", response_model=PlatformEventCatalogResponse)
async def platform_events_catalog(di: Di) -> PlatformEventCatalogResponse:
    return await op_flows_platform_events_catalog(
        EmptyPayload(),
        user=require_context().user,
        di=di,
    )
