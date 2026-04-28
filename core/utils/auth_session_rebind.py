"""
Перевыпуск session JWT и cookie при смене активной компании (инвайт, host-wins в middleware).
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from starlette.responses import Response

from core.config import get_settings
from core.models.identity_models import User
from core.utils.domain import get_cookie_domain
from core.utils.tokens import TokenData, TokenService, get_token_service


def attach_session_auth_cookie(response: Response, request: Request, token: str) -> None:
    if not token or not str(token).strip():
        raise ValueError("attach_session_auth_cookie: token required")
    settings = get_settings()
    cookie_domain = get_cookie_domain(request.headers.get("host", ""))
    is_production = settings.server.env == "production"
    response.set_cookie(
        key="auth_token",
        value=token,
        domain=cookie_domain,
        httponly=True,
        secure=is_production,
        samesite="lax",
        max_age=TokenService.SESSION_EXPIRES,
    )


def _normalize_roles(raw: object) -> list[str]:
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(x) for x in raw]
    raise ValueError("rebind_session_to_company: roles must be str or list")


async def rebind_session_to_company(
    *,
    container: Any,
    user: User,
    company: Any,
    roles: list[str] | None = None,
) -> tuple[str, TokenData]:
    """
    active_company_id = company.company_id, сохранение user, новый SESSION JWT.
    company — модель Company с полем company_id.
    """
    cid = company.company_id
    if cid not in user.companies:
        raise ValueError(
            f"rebind_session_to_company: user {user.user_id} is not a member of {cid}"
        )
    if roles is None:
        roles = _normalize_roles(user.companies[cid])
    if len(roles) == 0:
        raise ValueError("rebind_session_to_company: roles must be non-empty")

    user.active_company_id = cid
    await container.user_repository.set(user)

    token_service = get_token_service()
    raw = token_service.create_token(user.user_id, cid, roles=roles)
    td = token_service.validate_token(raw)
    if td is None:
        raise RuntimeError("rebind_session_to_company: validate_token failed for new session")
    return raw, td
