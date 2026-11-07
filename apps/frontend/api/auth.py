"""Роутер авторизации для Frontend сервиса."""

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from apps.frontend.di import Di
from core.config import get_settings
from core.identity.auth_service import AuthService
from core.logging import get_logger
from core.models.identity_models import AuthProvider, AuthRequest, Company
from core.utils.domain import build_url, get_cookie_domain, is_local
from core.utils.tokens import TokenService
from core.websocket import WsCommandError

logger = get_logger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/callback")
async def auth_callback(
    request: Request,
    di: Di,
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
    provider: Annotated[str | None, Query()] = None,
    apple_oauth_user_json: Annotated[str | None, Query(alias="user")] = None,
) -> RedirectResponse:
    """Callback после OAuth авторизации"""
    auth_service: AuthService = di.auth_service

    auth_state = await auth_service.peek_auth_state(state)
    if not auth_state:
        raise WsCommandError("ws_invalid_payload", "Invalid state", error_code="ws_invalid_payload")

    if provider is None:
        provider_enum = auth_state.provider
    else:
        try:
            provider_enum = AuthProvider(provider.lower())
        except ValueError:
            raise WsCommandError(
                "ws_invalid_payload",
                f"Unknown provider: {provider}",
                error_code="ws_invalid_payload",
            )

    original_host = auth_state.original_host
    return_path = auth_state.return_path
    redirect_uri = auth_state.redirect_uri

    auth_request = AuthRequest(
        provider=provider_enum,
        code=code,
        state=state,
        redirect_uri=redirect_uri,
        oauth_first_login_user_json=apple_oauth_user_json,
    )

    result = await auth_service.complete_auth(auth_request)

    if not result.success:
        return RedirectResponse(url=f"/?error={result.error_message}")
    if result.user is None or result.token is None:
        raise WsCommandError(
            "internal",
            "OAuth result is missing user or token",
            error_code="internal",
        )

    settings = get_settings()
    is_production = settings.server.env == "production"

    user = result.user
    token = result.token

    # Используем оригинальный хост для редиректа (если был субдомен)
    target_host = original_host or request.headers.get("host", "localhost:8002")

    # Если был запрошен возврат на конкретный путь — используем его
    if return_path:
        scheme = "http" if is_local(target_host) else "https"
        # Допускаем только пути (начинаются с /), не внешние URL
        if return_path.startswith("/"):
            redirect_url = f"{scheme}://{target_host}{return_path}"
        else:
            redirect_url = build_url(target_host, "/select-company")
    elif not user.companies or len(user.companies) == 0:
        redirect_url = build_url(target_host, "/select-company?action=create")
    elif len(user.companies) == 1:
        company_id = list(user.companies.keys())[0]
        company = await Company.get(company_id)
        if not company or not company.subdomain:
            redirect_url = build_url(target_host, "/select-company?action=create")
        else:
            redirect_url = build_url(target_host, "/dashboard", company.subdomain)
    else:
        active_id = user.active_company_id
        if active_id and active_id in user.companies:
            company = await Company.get(active_id)
            if company and company.subdomain:
                redirect_url = build_url(target_host, "/dashboard", company.subdomain)
            else:
                redirect_url = build_url(target_host, "/select-company")
        else:
            redirect_url = build_url(target_host, "/select-company")

    response = RedirectResponse(url=redirect_url)

    # Устанавливаем cookie для всех субдоменов базового домена
    cookie_domain = get_cookie_domain(target_host)

    # SESSION JWT = Centrifugo connection JWT; client reads auth_token via document.cookie.
    response.set_cookie(
        key="auth_token",
        value=token,
        domain=cookie_domain,
        httponly=False,
        secure=is_production,
        samesite="lax",
        max_age=TokenService.SESSION_EXPIRES,
    )

    return response
