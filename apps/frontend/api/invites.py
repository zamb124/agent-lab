"""
API для приглашений в компанию по ссылке.

Генерация: POST /api/invites/generate — owner/admin компании.
Просмотр: POST /api/invites/preview  — публично, по short_code (компания, роль, пригласивший).
Принятие: POST /api/invites/accept   — любой авторизованный пользователь.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from apps.frontend.dependencies import ContainerDep
from core.utils.auth_session_rebind import attach_session_auth_cookie, rebind_session_to_company
from core.utils.invite_tokens import (
    INVITE_EXPIRES_SECONDS,
    burn_invite_token,
    get_invite_token_service,
    invite_jti_already_used,
)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/invites", tags=["invites"])

VALID_ROLES = ["owner", "admin", "developer", "viewer"]


def _company_subdomain_for_response(company) -> str:
    raw = company.subdomain
    if raw is None or not isinstance(raw, str) or raw.strip() == "":
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
    token, _ = svc.create(
        company_id=company.company_id,
        role=body.role,
        invited_by=user.user_id,
    )

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=INVITE_EXPIRES_SECONDS)
    short = container.short_link_service
    invite_url = await short.mint_company_invite(token, expires_at)

    logger.info(
        f"Сгенерирован инвайт для компании {company.company_id}, "
        f"роль={body.role}, инициатор={user.user_id}"
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
):
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
        existing_roles = company.members[user.user_id]
        roles_list = existing_roles if isinstance(existing_roles, list) else [existing_roles]
        logger.info(
            f"Пользователь {user.user_id} уже участник компании {company.company_id}"
        )
        new_session_token, _ = await rebind_session_to_company(
            container=container,
            user=user,
            company=company,
            roles=roles_list,
        )

        response = JSONResponse(
            content=AcceptInviteResponse(
                company_id=company.company_id,
                company_name=company.name,
                role=roles_list,
                already_member=True,
                subdomain=_company_subdomain_for_response(company),
            ).model_dump()
        )
        attach_session_auth_cookie(response, request, new_session_token)
        return response

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

    await short.delete_by_code(code)

    new_session_token, _ = await rebind_session_to_company(
        container=container,
        user=user,
        company=company,
        roles=roles,
    )

    response = JSONResponse(
        content=AcceptInviteResponse(
            company_id=company.company_id,
            company_name=company.name,
            role=roles,
            already_member=False,
            subdomain=_company_subdomain_for_response(company),
        ).model_dump()
    )
    attach_session_auth_cookie(response, request, new_session_token)
    return response
