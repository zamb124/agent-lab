"""
API для приглашений в компанию по ссылке.

Генерация: POST /api/invites/generate — owner/admin компании.
Просмотр: POST /api/invites/preview  — публично, по short_code (компания, роль, пригласивший).
Принятие: POST /api/invites/accept   — любой авторизованный пользователь.
"""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from apps.frontend.dependencies import ContainerDep
from core.context import get_context
from core.logging import get_logger
from core.models.identity_models import Company, User
from core.utils.auth_session_rebind import attach_session_auth_cookie, rebind_session_to_company
from core.utils.invite_tokens import (
    INVITE_EXPIRES_SECONDS,
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
            detail="У компании не задан субдомен для входа.",
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
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    return context.user


def _require_invite_company() -> Company:
    context = get_context()
    if context is None:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    company = context.active_company
    if company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    return company


@router.post("/generate", response_model=GenerateInviteResponse)
async def generate_invite(
    body: GenerateInviteRequest,
    container: ContainerDep,
) -> GenerateInviteResponse:
    """
    Генерирует одноразовую ссылку-приглашение в компанию.
    Доступно только owner/admin компании.
    """
    user = _require_invite_user()
    company = _require_invite_company()

    member_roles = company.members.get(user.user_id, [])
    is_owner_or_admin = "owner" in member_roles or "admin" in member_roles
    is_owner_by_company_record = company.owner_user_id == user.user_id
    if not is_owner_or_admin and not is_owner_by_company_record:
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимая роль. Допустимые: {', '.join(VALID_ROLES)}",
        )

    svc = get_invite_token_service()
    token, _ = svc.create(
        company_id=company.company_id,
        role=body.role,
        invited_by=user.user_id,
    )

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=INVITE_EXPIRES_SECONDS)
    short = container.short_link_service
    invite_url = await short.mint_company_invite(token, expires_at)

    logger.info(
        "Сгенерирован инвайт для компании %s, роль=%s, инициатор=%s",
        company.company_id,
        body.role,
        user.user_id,
    )

    return GenerateInviteResponse(
        invite_url=invite_url,
        role=body.role,
        expires_in_seconds=INVITE_EXPIRES_SECONDS,
    )

@router.post("/preview", response_model=PreviewInviteResponse)
async def preview_invite(
    body: PreviewInviteRequest,
    container: ContainerDep,
) -> PreviewInviteResponse:
    """
    Возвращает данные приглашения для экрана /join без авторизации.
    Не расходует одноразовый токен.
    """
    code = body.short_code.strip()
    if code == "":
        raise HTTPException(status_code=400, detail="Код приглашения не задан")

    short = container.short_link_service
    jwt_str = await short.get_invite_jwt_by_code(code)
    if jwt_str is None:
        raise HTTPException(status_code=404, detail="Ссылка-приглашение не найдена или истекла")

    svc = get_invite_token_service()
    try:
        invite = svc.validate(jwt_str)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=410, detail="Ссылка-приглашение устарела")
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status_code=403, detail="Недействительная ссылка-приглашение")

    if await invite_jti_already_used(invite.jti):
        raise HTTPException(status_code=410, detail="Ссылка-приглашение уже была использована")

    company_repo = container.company_repository
    company = await company_repo.get(invite.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Компания не найдена или была удалена")

    user_repo = container.user_repository
    inviter = await user_repo.get(invite.invited_by)
    if not inviter:
        raise HTTPException(status_code=404, detail="Инициатор приглашения не найден")

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
    container: ContainerDep,
) -> AcceptInviteResponse:
    """
    Принимает инвайт-токен и добавляет пользователя в компанию.

    Идемпотентен: если пользователь уже участник — возвращает успех
    без расхода одноразового токена.
    """
    user = _require_invite_user()

    code = body.short_code.strip()
    if code == "":
        raise HTTPException(status_code=400, detail="Код приглашения не задан")

    short = container.short_link_service
    jwt_str = await short.get_invite_jwt_by_code(code)
    if jwt_str is None:
        raise HTTPException(status_code=404, detail="Ссылка-приглашение не найдена или истекла")

    svc = get_invite_token_service()
    try:
        invite = svc.validate(jwt_str)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=410, detail="Ссылка-приглашение устарела")
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status_code=403, detail="Недействительная ссылка-приглашение")

    company_repo = container.company_repository
    company = await company_repo.get(invite.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Компания не найдена или была удалена")

    # Уже участник: не расходуем одноразовый токен; активная компания и JWT
    # совпадают с компанией приглашения (тот же перевыпуск, что host-wins в middleware).
    if user.user_id in company.members:
        roles_list = list(company.members[user.user_id])
        logger.info(
            "Пользователь %s уже участник компании %s",
            user.user_id,
            company.company_id,
        )
        new_session_token, _ = await rebind_session_to_company(
            container=container,
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
        raise HTTPException(status_code=410, detail="Ссылка-приглашение уже была использована")

    # Добавляем пользователя в компанию
    roles = [invite.role]
    company.members[user.user_id] = roles
    _ = await company_repo.set(company)

    user_repo = container.user_repository
    user.companies[company.company_id] = roles
    user.active_company_id = company.company_id
    _ = await user_repo.set(user)

    logger.info(
        "Пользователь %s вступил в компанию %s с ролью %s",
        user.user_id,
        company.company_id,
        invite.role,
    )

    _ = await short.delete_by_code(code)

    new_session_token, _ = await rebind_session_to_company(
        container=container,
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
