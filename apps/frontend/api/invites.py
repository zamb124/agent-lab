"""
API для приглашений в компанию по ссылке.

Генерация: POST /api/invites/generate — REST-зеркало `frontend/invites/generate_requested`.
Просмотр: POST /api/invites/preview  — публично, по short_code (компания, роль, пригласивший).
Принятие: POST /api/invites/accept   — любой авторизованный пользователь.
"""

from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from apps.frontend.di import Di
from apps.frontend.realtime.company_operations import (
    InviteGenerated,
    InviteGeneratePayload,
    op_invites_generate,
)
from core.context import get_context, require_context
from core.identity.company_membership import (
    set_company_member_roles,
    sync_existing_company_member,
)
from core.logging import get_logger
from core.models.identity_models import Company, User
from core.namespace import ensure_personal_namespace_for_user
from core.short_links.models import PlatformShortLink
from core.utils.auth_session_rebind import attach_session_auth_cookie, rebind_session_to_company
from core.utils.invite_tokens import (
    burn_invite_token,
    get_invite_token_service,
    invite_jti_already_used,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/invites", tags=["invites"])

VALID_ROLES = ["owner", "admin", "developer", "viewer"]


def _company_subdomain_for_response(company: Company) -> str:
    raw = company.subdomain
    if raw is None or raw.strip() == "":
        raise HTTPException(
            status_code=403,
            detail="Company has no subdomain for sign-in.",
        )
    return raw.strip()

class GenerateInviteRequest(BaseModel):
    role: str = "developer"

class GenerateInviteResponse(BaseModel):
    invite_url: str
    role: str
    expires_in_seconds: int

class AcceptInviteRequest(BaseModel):
    short_code: str

class AcceptInviteResponse(BaseModel):
    company_id: str
    company_name: str
    role: list[str]
    already_member: bool
    subdomain: str

class PreviewInviteRequest(BaseModel):
    short_code: str

class PreviewInviteResponse(BaseModel):
    company_id: str
    company_name: str
    role: str
    invited_by_user_id: str
    invited_by_name: str


def _require_invite_user() -> User:
    context = get_context()
    if context is None:
        raise HTTPException(status_code=401, detail="Authorization is required")
    return context.user



@router.post("/generate", response_model=InviteGenerated)
async def generate_invite(body: InviteGeneratePayload, di: Di) -> InviteGenerated:
    return await op_invites_generate(body, user=require_context().user, di=di)


@router.post("/preview", response_model=PreviewInviteResponse)
async def preview_invite(
    body: PreviewInviteRequest,
    di: Di,
) -> PreviewInviteResponse:
    """
    Возвращает данные приглашения для экрана /join без авторизации.
    Не расходует одноразовый токен.
    """
    code = body.short_code.strip()
    if code == "":
        raise HTTPException(status_code=400, detail="Invite code is not set")

    short = di.short_link_service
    jwt_str = await short.get_invite_jwt_by_code(code)
    if jwt_str is None:
        raise HTTPException(status_code=404, detail="Invite link not found or expired")

    svc = get_invite_token_service()
    try:
        invite = svc.validate(jwt_str)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=410, detail="Invite link is stale")
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status_code=403, detail="Invalid invite link")

    if await invite_jti_already_used(invite.jti):
        raise HTTPException(status_code=410, detail="Invite link has already been used")

    company = await Company.get(invite.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found or was deleted")

    inviter = await User.get(invite.invited_by)
    if not inviter:
        raise HTTPException(status_code=404, detail="Invite initiator not found")

    return PreviewInviteResponse(
        company_id=company.company_id,
        company_name=company.name,
        role=invite.role,
        invited_by_user_id=inviter.user_id,
        invited_by_name=inviter.name,
    )

@router.post("/accept", response_model=AcceptInviteResponse)
async def accept_invite(
    body: AcceptInviteRequest,
    request: Request,
    response: Response,
    di: Di,
) -> AcceptInviteResponse:
    """
    Принимает инвайт-токен и добавляет пользователя в компанию.

    Идемпотентен: если пользователь уже участник — возвращает успех
    без расхода одноразового токена.
    """
    user = _require_invite_user()

    code = body.short_code.strip()
    if code == "":
        raise HTTPException(status_code=400, detail="Invite code is not set")

    short = di.short_link_service
    jwt_str = await short.get_invite_jwt_by_code(code)
    if jwt_str is None:
        raise HTTPException(status_code=404, detail="Invite link not found or expired")

    svc = get_invite_token_service()
    try:
        invite = svc.validate(jwt_str)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=410, detail="Invite link is stale")
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status_code=403, detail="Invalid invite link")

    company = await Company.get(invite.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found or was deleted")

    # Уже участник: не расходуем одноразовый токен; активная компания и JWT
    # совпадают с компанией приглашения (тот же перевыпуск, что host-wins в middleware).
    if user.user_id in company.members:
        roles_list = list(company.members[user.user_id])
        logger.info("frontend.event", user_id=user.user_id, company_id=company.company_id)
        await sync_existing_company_member(
            authz=di.authz_service,
            company_id=company.company_id,
            user_id=user.user_id,
            roles=roles_list,
        )
        new_session_token, _ = await rebind_session_to_company(
            user=user,
            company=company,
            roles=roles_list,
        )

        attach_session_auth_cookie(response, request, new_session_token)
        return AcceptInviteResponse(
            company_id=company.company_id,
            company_name=company.name,
            role=roles_list,
            already_member=True,
            subdomain=_company_subdomain_for_response(company),
        )

    # Сжигаем токен атомарно
    remaining_seconds = max(
        1,
        int((invite.exp - datetime.now(timezone.utc)).total_seconds()),
    )
    burned = await burn_invite_token(invite.jti, ttl_seconds=remaining_seconds)
    if not burned:
        raise HTTPException(status_code=410, detail="Invite link has already been used")

    # Добавляем пользователя в компанию
    roles = [invite.role]
    roles = await set_company_member_roles(
        authz=di.authz_service,
        company=company,
        user=user,
        roles=roles,
    )
    user.active_company_id = company.company_id
    _ = await User.set(user)

    await ensure_personal_namespace_for_user(
        di.namespace_service,
        user,
        company=company,
    )

    logger.info(
        "frontend.event",
        user_id=user.user_id,
        company_id=company.company_id,
        role=invite.role,
    )

    _ = await PlatformShortLink.delete_by_id(code)

    new_session_token, _ = await rebind_session_to_company(
        user=user,
        company=company,
        roles=roles,
    )

    attach_session_auth_cookie(response, request, new_session_token)
    return AcceptInviteResponse(
        company_id=company.company_id,
        company_name=company.name,
        role=roles,
        already_member=False,
        subdomain=_company_subdomain_for_response(company),
    )
