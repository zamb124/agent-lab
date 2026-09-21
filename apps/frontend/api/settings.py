"""REST-зеркало команд `frontend/company_settings/*`."""

from fastapi import APIRouter

from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import (
    CompanySettingsResponse,
    CompanySettingsUpdate,
    CompanySettingsUpdateResponse,
)
from apps.frontend.realtime.company_operations import (
    op_company_settings_get,
    op_company_settings_update,
)
from core.context import require_context
from core.websocket import EmptyPayload

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/company", response_model=CompanySettingsResponse)
async def get_company_settings(container: ContainerDep) -> CompanySettingsResponse:
    return await op_company_settings_get(
        EmptyPayload(), user=require_context().user, container=container
    )


@router.patch("/company", response_model=CompanySettingsUpdateResponse)
async def update_company_settings(
    update: CompanySettingsUpdate,
    container: ContainerDep,
) -> CompanySettingsUpdateResponse:
    return await op_company_settings_update(update, user=require_context().user, container=container)
