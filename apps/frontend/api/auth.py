"""
Роутер авторизации для Frontend сервиса
"""
import logging
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, JSONResponse
from core.identity.auth_service import AuthService
from core.models.identity_models import AuthProvider, AuthRequest
from core.config import get_settings
from core.utils.domain import get_cookie_domain, build_url
from apps.frontend.dependencies import get_container

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/callback")
async def auth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    provider: str = Query(None)
):
    """Callback после OAuth авторизации"""
    from core.utils.domain import is_local, get_host_with_port
    
    container = get_container()
    auth_service: AuthService = container.auth_service
    
    auth_state = await auth_service._get_auth_state(state)
    if not auth_state:
        raise HTTPException(status_code=400, detail="Недействительный state")
    
    if not provider:
        provider = auth_state.get("provider")
    
    try:
        provider_enum = AuthProvider(provider.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Неизвестный провайдер: {provider}")
    
    # Получаем оригинальный хост из state (субдомен откуда пользователь пришел)
    original_host = auth_state.get("original_host")

    # Опциональный путь для возврата после авторизации (напр. /join?token=...)
    return_path = auth_state.get("return_path")

    # redirect_uri должен совпадать с тем что был при start_auth (на базовом домене)
    redirect_uri = auth_state.get("redirect_uri")
    
    auth_request = AuthRequest(
        provider=provider_enum,
        code=code,
        state=state,
        redirect_uri=redirect_uri
    )
    
    result = await auth_service.complete_auth(auth_request)
    
    if not result.success:
        return RedirectResponse(url=f"/?error={result.error_message}")
    
    settings = get_settings()
    is_production = settings.server.env == "production"
    
    user = result.user
    
    # Используем оригинальный хост для редиректа (если был субдомен)
    target_host = original_host or request.headers.get("host", "localhost:8002")

    # Если был запрошен возврат на конкретный путь — используем его
    if return_path:
        from core.utils.domain import is_local
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
        value=result.token,
        domain=cookie_domain,
        httponly=True,
        secure=is_production,
        samesite="lax",
        max_age=7200
    )
    
    return response


@router.post("/logout")
async def logout(request: Request):
    """Выйти из системы"""
    cookie_domain = get_cookie_domain(request.headers.get("host", ""))
    
    response = JSONResponse({"success": True})
    response.delete_cookie("auth_token", domain=cookie_domain)
    return response

