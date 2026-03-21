"""
API для приглашений в компанию по ссылке.

Генерация: POST /api/invites/generate — owner/admin компании.
Принятие:  POST /api/invites/accept   — любой авторизованный пользователь.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from apps.frontend.dependencies import ContainerDep
from core.config import get_settings
from core.utils.domain import get_cookie_domain
from core.utils.invite_tokens import (
    INVITE_EXPIRES_SECONDS,
    burn_invite_token,
    get_invite_token_service,
)
from core.utils.tokens import get_token_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/invites", tags=["invites"])

VALID_ROLES = ["owner", "admin", "developer", "viewer"]


class GenerateInviteRequest(BaseModel):
    role: str = "developer"


class GenerateInviteResponse(BaseModel):
    invite_url: str
    role: str
    expires_in_seconds: int


class AcceptInviteRequest(BaseModel):
    token: str


class AcceptInviteResponse(BaseModel):
    company_id: str
    company_name: str
    role: list[str]
    already_member: bool


def _require_user(request: Request):
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    return request.state.user


def _require_company(request: Request):
    if not hasattr(request.state, "company") or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    return request.state.company


@router.post("/generate", response_model=GenerateInviteResponse)
async def generate_invite(
    body: GenerateInviteRequest,
    request: Request,
    container: ContainerDep,
):
    """
    Генерирует одноразовую ссылку-приглашение в компанию.
    Доступно только owner/admin компании.
    """
    user = _require_user(request)
    company = _require_company(request)

    member_roles = company.members.get(user.user_id, [])
    if isinstance(member_roles, str):
        member_roles = [member_roles]
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
    token, _ = svc.create(company_id=company.company_id, role=body.role)

    host = request.headers.get("host", "")
    scheme = "https" if request.headers.get("x-forwarded-proto") == "https" else "http"
    invite_url = f"{scheme}://{host}/join?token={token}"

    logger.info(
        f"Сгенерирован инвайт для компании {company.company_id}, "
        f"роль={body.role}, инициатор={user.user_id}"
    )

    return GenerateInviteResponse(
        invite_url=invite_url,
        role=body.role,
        expires_in_seconds=INVITE_EXPIRES_SECONDS,
    )


@router.post("/accept")
async def accept_invite(
    body: AcceptInviteRequest,
    request: Request,
    container: ContainerDep,
):
    """
    Принимает инвайт-токен и добавляет пользователя в компанию.

    Идемпотентен: если пользователь уже участник — возвращает успех
    без расхода одноразового токена.
    """
    user = _require_user(request)

    svc = get_invite_token_service()
    try:
        invite = svc.validate(body.token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=410, detail="Ссылка-приглашение устарела")
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status_code=403, detail="Недействительная ссылка-приглашение")

    company_repo = container.company_repository
    company = await company_repo.get(invite.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Компания не найдена или была удалена")

    # Если пользователь уже участник — идемпотентный успех без расхода токена
    if user.user_id in company.members:
        existing_roles = company.members[user.user_id]
        logger.info(
            f"Пользователь {user.user_id} уже участник компании {company.company_id}"
        )
        return AcceptInviteResponse(
            company_id=company.company_id,
            company_name=company.name,
            role=existing_roles if isinstance(existing_roles, list) else [existing_roles],
            already_member=True,
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
    await company_repo.set(company)

    user_repo = container.user_repository
    user.companies[company.company_id] = roles
    user.active_company_id = company.company_id
    await user_repo.set(user)

    logger.info(
        f"Пользователь {user.user_id} вступил в компанию {company.company_id} "
        f"с ролью {invite.role}"
    )

    # Перевыпускаем сессионный токен с новым company_id
    token_service = get_token_service()
    new_session_token = token_service.create_token(user.user_id, company.company_id, roles=roles)

    settings = get_settings()
    cookie_domain = get_cookie_domain(request.headers.get("host", ""))
    is_production = settings.server.env == "production"

    response = JSONResponse(
        content=AcceptInviteResponse(
            company_id=company.company_id,
            company_name=company.name,
            role=roles,
            already_member=False,
        ).model_dump()
    )
    response.set_cookie(
        key="auth_token",
        value=new_session_token,
        domain=cookie_domain,
        httponly=True,
        secure=is_production,
        samesite="lax",
        max_age=7200,
    )
    return response
