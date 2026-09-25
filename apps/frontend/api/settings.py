"""REST-зеркало команд `frontend/company_settings/*`."""

from fastapi import APIRouter

from apps.frontend.di import Di
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
async def get_company_settings(di: Di) -> CompanySettingsResponse:
    return await op_company_settings_get(
        EmptyPayload(), user=require_context().user, di=di
    )


@router.patch("/company", response_model=CompanySettingsUpdateResponse)
async def update_company_settings(
    update: CompanySettingsUpdate,
    di: Di,
) -> CompanySettingsUpdateResponse:
    return await op_company_settings_update(update, user=require_context().user, di=di)
