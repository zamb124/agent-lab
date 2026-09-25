"""REST-зеркало команд `frontend/companies/*`; `GET /me` даёт core-роутер `core/api/companies.py`."""

from fastapi import APIRouter, Request, Response

from apps.frontend.di import Di
from apps.frontend.realtime.companies_operations import (
    CompanyCreated,
    CompanyCreatePayload,
    CompanySlugCheckPayload,
    CompanySlugCheckResult,
    SystemAccessGranted,
    SystemAccessGrantPayload,
    SystemAccessRevoked,
    SystemAccessRevokePayload,
    op_companies_create,
    op_companies_slug_check,
    op_companies_system_access_grant,
    op_companies_system_access_revoke,
)
from core.context import require_context
from core.models import StrictBaseModel
from core.models.identity_models import SYSTEM_COMPANY_ID
from core.utils.auth_session_rebind import attach_session_auth_cookie
from core.utils.tokens import get_token_service

router = APIRouter(prefix="/api/companies", tags=["public", "companies"])


class CreateCompanyRequest(StrictBaseModel):
    name: str
    slug: str


class SystemAccessRequest(StrictBaseModel):
    role: str


@router.post("/check-slug", response_model=CompanySlugCheckResult)
async def check_slug(body: CompanySlugCheckPayload, di: Di) -> CompanySlugCheckResult:
    return await op_companies_slug_check(body, user=require_context().user, di=di)


@router.post("", response_model=CompanyCreated)
async def create_company(
    request_body: CreateCompanyRequest, request: Request, response: Response, di: Di
) -> CompanyCreated:
    """Создание компании; SESSION JWT перевыпускается на неё в cookie (граница HTTP)."""
    user = require_context().user
    created = await op_companies_create(
        CompanyCreatePayload(
            name=request_body.name, slug=request_body.slug, public_host=request.headers.get("host", "")
        ),
        user=user,
        di=di,
    )
    session_token = get_token_service().create_token(user.user_id, created.company_id, email=user.email)
    attach_session_auth_cookie(response, request, session_token)
    return created


@router.post("/{company_id}/system-access", response_model=SystemAccessGranted)
async def enter_company_as_system_member(
    company_id: str, payload: SystemAccessRequest, di: Di
) -> SystemAccessGranted:
    return await op_companies_system_access_grant(
        SystemAccessGrantPayload(company_id=company_id, role=payload.role),
        user=require_context().user,
        di=di,
    )


@router.delete("/{company_id}/system-access", response_model=SystemAccessRevoked)
async def leave_company_as_system_member(
    company_id: str, request: Request, response: Response, di: Di
) -> SystemAccessRevoked:
    user = require_context().user
    revoked = await op_companies_system_access_revoke(
        SystemAccessRevokePayload(company_id=company_id), user=user, di=di
    )
    if revoked.switched_to_system:
        system_roles = user.companies.get(SYSTEM_COMPANY_ID)
        if not system_roles:
            raise ValueError("User has no roles in the system company")
        refreshed_token = get_token_service().create_token(
            user_id=user.user_id, company_id=SYSTEM_COMPANY_ID, roles=system_roles, email=user.email
        )
        attach_session_auth_cookie(response, request, refreshed_token)
    return revoked
