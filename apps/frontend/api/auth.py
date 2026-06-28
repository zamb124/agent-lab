"""Роутер авторизации для Frontend сервиса."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from apps.frontend.dependencies import ContainerDep
from core.config import get_settings
from core.identity.auth_service import AuthService
from core.logging import get_logger
from core.models.identity_models import AuthProvider, AuthRequest
from core.utils.domain import build_url, get_cookie_domain, is_local
from core.utils.tokens import TokenService

logger = get_logger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/callback")
async def auth_callback(
    request: Request,
    container: ContainerDep,
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
    provider: Annotated[str | None, Query()] = None,
    apple_oauth_user_json: Annotated[str | None, Query(alias="user")] = None,
) -> RedirectResponse:
    """Callback после OAuth авторизации"""
    auth_service: AuthService = container.auth_service

    auth_state = await auth_service.get_auth_state(state)
    if not auth_state:
        raise HTTPException(status_code=400, detail="Недействительный state")

    if provider is None:
        provider_enum = auth_state.provider
    else:
        try:
            provider_enum = AuthProvider(provider.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Неизвестный провайдер: {provider}")

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
        raise HTTPException(status_code=500, detail="OAuth result is missing user or token")

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
        company = await container.company_repository.get(company_id)
        if not company or not company.subdomain:
            redirect_url = build_url(target_host, "/select-company?action=create")
        else:
            redirect_url = build_url(target_host, "/dashboard", company.subdomain)
    else:
        active_id = user.active_company_id
        if active_id and active_id in user.companies:
            company = await container.company_repository.get(active_id)
            if company and company.subdomain:
                redirect_url = build_url(target_host, "/dashboard", company.subdomain)
            else:
                redirect_url = build_url(target_host, "/select-company")
        else:
            redirect_url = build_url(target_host, "/select-company")

    response = RedirectResponse(url=redirect_url)

    # Устанавливаем cookie для всех субдоменов базового домена
    cookie_domain = get_cookie_domain(target_host)

    response.set_cookie(
        key="auth_token",
        value=token,
        domain=cookie_domain,
        httponly=True,
        secure=is_production,
        samesite="lax",
        max_age=TokenService.SESSION_EXPIRES,
    )

    return response
