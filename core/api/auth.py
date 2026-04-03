"""
API эндпоинты для авторизации.

Общий роутер для авторизации, может использоваться в любом сервисе.
Контейнер получается через request.app.state.container.
"""

import logging
from typing import Annotated, Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Request, Depends, Form, Query
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, Field as PydanticField
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core.config import get_settings
from core.models import AuthProvider, AuthRequest
from core.identity import AuthService
from core.utils.tokens import TokenService, get_token_service
from core.utils.domain import get_cookie_domain, build_url

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


class UserUpdate(BaseModel):
    """Обновление данных пользователя"""
    name: Optional[str] = PydanticField(None, max_length=200)
    first_name: Optional[str] = PydanticField(None, max_length=100)
    last_name: Optional[str] = PydanticField(None, max_length=100)
    emails: Optional[List[str]] = None
    phones: Optional[List[str]] = None
    messengers: Optional[Dict[str, str]] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = PydanticField(None, max_length=4000)
    ui_preferences: Optional[Dict[str, Any]] = None


class SwitchCompanyRequest(BaseModel):
    """Переключение активной компании пользователя"""
    company_id: str


class DemoLoginRequest(BaseModel):
    email: str
    password: str


def get_auth_service(request: Request) -> AuthService:
    """Получает AuthService из контейнера приложения"""
    return request.app.state.container.auth_service


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def _clear_platform_auth_cookies(response: JSONResponse, request: Request) -> None:
    """
    Удаляет куки входа с теми же path/domain/secure/samesite (и httponly для auth_token),
    с какими они выставляются в login/demo, OAuth callback и switch-company.
    """
    settings = get_settings()
    is_production = settings.server.env == "production"
    host = request.headers.get("host", "")
    cookie_domain = get_cookie_domain(host)
    for httponly_auth in (False, True):
        response.delete_cookie(
            key="auth_token",
            path="/",
            domain=cookie_domain,
            secure=is_production,
            httponly=httponly_auth,
            samesite="lax",
        )
    response.delete_cookie(
        key="session_id",
        path="/",
        domain=cookie_domain,
        secure=is_production,
        httponly=True,
        samesite="lax",
    )


def _append_query(url: str, params: Dict[str, str]) -> str:
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(params)
    next_query = urlencode(query)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, next_query, parsed.fragment))


@router.get("/demo/status")
async def demo_auth_status():
    """Публичный флаг: включён ли демо-вход (без утечки email, если выключено)."""
    settings = get_settings()
    demo = settings.auth.demo
    if not demo.login_enabled:
        return {"enabled": False}
    return {"enabled": True, "email": demo.email}


@router.post("/login/demo")
async def login_demo(
    request: Request,
    body: DemoLoginRequest,
    auth_service: AuthServiceDep,
):
    """Вход демо-пользователя (cookies как после OAuth)."""
    settings = get_settings()
    result = await auth_service.login_demo(body.email, body.password)

    if not result.success or not result.session or not result.token or not result.user:
        raise HTTPException(
            status_code=401,
            detail=result.error_message or "Неверные учётные данные",
        )

    target_host = request.headers.get("host", "")
    redirect_url = build_url(
        target_host,
        "/dashboard",
        settings.auth.demo.subdomain,
    )

    response = JSONResponse(
        content={"redirect_url": redirect_url, "success": True},
    )
    is_production = settings.server.env == "production"
    cookie_domain = get_cookie_domain(target_host)
    cookie_max_age = TokenService.SESSION_EXPIRES

    response.set_cookie(
        key="session_id",
        value=result.session.session_id,
        domain=cookie_domain,
        httponly=True,
        secure=is_production,
        samesite="lax",
        max_age=cookie_max_age,
    )
    response.set_cookie(
        key="auth_token",
        value=result.token,
        domain=cookie_domain,
        httponly=False,
        secure=is_production,
        samesite="lax",
        max_age=cookie_max_age,
    )

    return response


@router.get("/providers")
async def get_auth_providers(auth_service: AuthServiceDep):
    """Возвращает список доступных провайдеров авторизации"""
    providers = auth_service.get_available_providers()

    return {
        "providers": [
            {
                "name": provider.value,
                "display_name": provider.value.title(),
                "auth_url": f"/api/v1/auth/login/{provider.value}",
            }
            for provider in providers
        ]
    }


@router.get("/login/{provider_name}")
async def start_auth(
    request: Request,
    provider_name: str,
    auth_service: AuthServiceDep,
    redirect_uri: str = None,
    return_path: str = None,
):
    """
    Начинает процесс авторизации с выбранным провайдером.

    Args:
        request: FastAPI request для определения redirect_uri
        provider_name: Имя провайдера (yandex, google, etc.)
        redirect_uri: URI для возврата после авторизации (опционально)
        
    Returns:
        JSON с auth_url для редиректа на стороне клиента
    """
    from core.utils.domain import is_local, get_host_with_port
    
    settings = get_settings()
    
    try:
        provider = AuthProvider(provider_name)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Неподдерживаемый провайдер: {provider_name}"
        )

    if provider == AuthProvider.DEMO:
        raise HTTPException(
            status_code=400,
            detail="Для демо-входа используйте POST /login/demo с полями email и password",
        )

    # Сохраняем оригинальный хост для редиректа после авторизации
    original_host = request.headers.get("host", "localhost:8002")
    
    if redirect_uri is None:
        # Определяем протокол
        forwarded_proto = request.headers.get("x-forwarded-proto")
        if forwarded_proto:
            protocol = forwarded_proto
        else:
            protocol = "http" if is_local(original_host) else "https"
        
        # Используем базовый домен (без субдомена) для OAuth redirect_uri
        # Это позволяет зарегистрировать один callback URL в провайдере
        base_host = get_host_with_port(original_host)
        
        # Единый OAuth callback на frontend gateway.
        callback_path = f"/auth/callback/{provider_name}"
        
        redirect_uri = f"{protocol}://{base_host}{callback_path}"
    
    logger.info(f"start_auth: original_host={original_host}, redirect_uri={redirect_uri}")

    try:
        auth_url = await auth_service.start_auth(
            provider,
            redirect_uri,
            original_host=original_host,
            return_path=return_path,
        )
        return {"auth_url": auth_url, "provider": provider_name}
    except ValueError as e:
        logger.error(f"Ошибка начала авторизации {provider_name}: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка начала авторизации {provider_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _complete_oauth_callback(
    request: Request,
    provider_name: str,
    code: Optional[str],
    state: Optional[str],
    auth_service: AuthService,
    error: Optional[str] = None,
    oauth_first_login_user_json: Optional[str] = None,
) -> RedirectResponse:
    """Общая логика GET/POST callback (Apple form_post передаёт поля в теле формы)."""
    from core.utils.domain import get_cookie_domain

    settings = get_settings()

    if error:
        logger.error(f"Ошибка авторизации от {provider_name}: {error}")
        raise HTTPException(status_code=400, detail=f"Ошибка авторизации: {error}")

    if not code or not state:
        raise HTTPException(
            status_code=400, detail="Отсутствуют обязательные параметры"
        )

    try:
        provider = AuthProvider(provider_name)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Неподдерживаемый провайдер: {provider_name}"
        )

    auth_state = await auth_service._get_auth_state(state)
    if not auth_state:
        if provider_name == AuthProvider.GOOGLE.value:
            calendar_service = request.app.state.container.calendar_service
            try:
                return_path = await calendar_service.complete_google_oauth(state=state, code=code)
            except ValueError as err:
                raise HTTPException(status_code=400, detail=str(err)) from err
            except Exception as err:
                raise HTTPException(status_code=500, detail=str(err)) from err
            redirect_url = _append_query(
                return_path,
                {
                    "calendar_provider": "google",
                    "calendar_status": "connected",
                },
            )
            return RedirectResponse(url=redirect_url)
        raise HTTPException(status_code=400, detail="Недействительный state")

    original_host = auth_state.get("original_host")
    redirect_uri = auth_state.get("redirect_uri")

    logger.info(f"auth_callback: redirect_uri={redirect_uri}, original_host={original_host}")

    auth_request = AuthRequest(
        provider=provider,
        code=code,
        state=state,
        redirect_uri=redirect_uri,
        oauth_first_login_user_json=oauth_first_login_user_json,
    )

    result = await auth_service.complete_auth(auth_request)

    logger.info(f"Результат авторизации: success={result.success}, error={result.error_message}")

    if not result.success:
        logger.error(f"Ошибка завершения авторизации: {result.error_message}")
        raise HTTPException(status_code=400, detail=result.error_message)

    target_host = original_host or request.headers.get("host", "")

    response = RedirectResponse(url="/select-company")
    is_production = settings.server.env == "production"

    cookie_domain = get_cookie_domain(target_host)

    logger.info(f"Устанавливаем cookies: session_id={result.session.session_id}, auth_token={result.token[:8]}..., domain={cookie_domain}, secure={is_production}")

    cookie_max_age = TokenService.SESSION_EXPIRES
    response.set_cookie(
        key="session_id",
        value=result.session.session_id,
        domain=cookie_domain,
        httponly=True,
        secure=is_production,
        samesite="lax",
        max_age=cookie_max_age,
    )
    response.set_cookie(
        key="auth_token",
        value=result.token,
        domain=cookie_domain,
        httponly=False,
        secure=is_production,
        samesite="lax",
        max_age=cookie_max_age,
    )

    logger.info(f"Успешная авторизация пользователя {result.user.user_id}")
    return response


@router.get("/callback/{provider_name}")
async def auth_callback(
    request: Request,
    provider_name: str,
    code: str,
    state: str,
    auth_service: AuthServiceDep,
    error: str = None,
    user: Optional[str] = None,
):
    """Callback после OAuth (query); Apple при scope name/email шлёт POST form_post."""
    return await _complete_oauth_callback(
        request,
        provider_name,
        code,
        state,
        auth_service,
        error=error,
        oauth_first_login_user_json=user,
    )


@router.post("/callback/{provider_name}")
async def auth_callback_post(
    request: Request,
    provider_name: str,
    auth_service: AuthServiceDep,
    code: str = Form(...),
    state: str = Form(...),
    error: Optional[str] = Form(None),
    user: Optional[str] = Form(None),
):
    """Sign in with Apple: response_mode=form_post — code/state/user в application/x-www-form-urlencoded."""
    return await _complete_oauth_callback(
        request,
        provider_name,
        code,
        state,
        auth_service,
        error=error,
        oauth_first_login_user_json=user,
    )


@router.post("/logout")
async def logout(
    request: Request,
    auth_service: AuthServiceDep,
    session_id: Annotated[Optional[str], Query()] = None,
):
    """
    Завершает сессию: берёт session_id из query (опционально) или из JWT в cookie,
    удаляет запись сессии и снимает auth_token/session_id в браузере.
    """
    token_data = getattr(request.state, "token_data", None)
    resolved_session_id = session_id or (
        token_data.session_id if token_data and token_data.session_id else None
    )
    if resolved_session_id:
        await auth_service.logout(resolved_session_id)

    response = JSONResponse({"success": True, "message": "Сессия завершена"})
    _clear_platform_auth_cookies(response, request)
    return response


@router.get("/me")
async def get_current_user(request: Request, auth_service: AuthServiceDep):
    """
    Возвращает полную информацию о текущем авторизованном пользователе.
    """
    token_data = getattr(request.state, "token_data", None)
    
    if not token_data:
        logger.warning("Запрос к /api/auth/me без авторизации")
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_repo = auth_service._user_repository
    user = await user_repo.get(token_data.user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "user_id": user.user_id,
        "name": user.name,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "status": user.status,
        "groups": user.groups,
        "companies": user.companies,
        "active_company_id": user.active_company_id,
        "company_id": token_data.company_id,
        "roles": token_data.roles,
        "emails": user.emails,
        "phones": user.phones,
        "messengers": user.messengers,
        "avatar_url": user.avatar_url,
        "bio": user.bio,
        "ui_preferences": user.ui_preferences,
        "attrs": user.attrs,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


@router.post("/switch-company")
async def switch_company(
    request: Request,
    payload: SwitchCompanyRequest,
    auth_service: AuthServiceDep,
):
    """Переключает активную компанию пользователя и перевыпускает auth_token."""
    token_data = getattr(request.state, "token_data", None)
    if not token_data:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_repo = auth_service._user_repository
    user = await user_repo.get(token_data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.company_id not in user.companies:
        raise HTTPException(status_code=403, detail="Нет доступа к выбранной компании")

    user.active_company_id = payload.company_id
    await user_repo.set(user)

    company_roles = user.companies[payload.company_id]
    token_service = get_token_service()
    new_token = token_service.create_token(
        user_id=user.user_id,
        company_id=payload.company_id,
        roles=company_roles,
        session_id=getattr(token_data, "session_id", None),
    )

    settings = get_settings()
    response = JSONResponse(content={"success": True, "company_id": payload.company_id})
    response.set_cookie(
        key="auth_token",
        value=new_token,
        domain=get_cookie_domain(request.headers.get("host", "")),
        httponly=True,
        secure=settings.server.env == "production",
        samesite="lax",
        max_age=TokenService.SESSION_EXPIRES,
    )
    return response


@router.put("/me")
async def update_current_user(
    request: Request,
    updates: "UserUpdate",
    auth_service: AuthServiceDep
):
    """
    Обновляет данные текущего пользователя.
    """
    from datetime import datetime, timezone
    
    token_data = getattr(request.state, "token_data", None)
    
    if not token_data:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_repo = auth_service._user_repository
    user = await user_repo.get(token_data.user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    update_data = updates.model_dump(exclude_none=True)

    for field, value in update_data.items():
        setattr(user, field, value)

    if "first_name" in update_data or "last_name" in update_data:
        parts: list[str] = []
        if user.first_name and user.first_name.strip():
            parts.append(user.first_name.strip())
        if user.last_name and user.last_name.strip():
            parts.append(user.last_name.strip())
        if parts:
            user.name = " ".join(parts)

    user.updated_at = datetime.now(timezone.utc)
    await user_repo.set(user)
    
    return {"success": True, "message": "User updated"}


@router.get("/me/attrs/{service}")
async def get_service_attrs(
    request: Request,
    service: str,
    auth_service: AuthServiceDep
):
    """
    Получает service-specific атрибуты для текущего пользователя.
    
    Args:
        service: Имя сервиса (crm, agents, rag)
    """
    token_data = getattr(request.state, "token_data", None)
    
    if not token_data:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_repo = auth_service._user_repository
    user = await user_repo.get(token_data.user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user.attrs.get(service, {})


@router.put("/me/attrs/{service}")
async def update_service_attrs(
    request: Request,
    service: str,
    attrs: Dict[str, Any],
    auth_service: AuthServiceDep
):
    """
    Обновляет service-specific атрибуты для текущего пользователя (merge).
    
    Args:
        service: Имя сервиса (crm, agents, rag)
        attrs: Атрибуты для обновления (merge с существующими)
    """
    from datetime import datetime, timezone
    
    token_data = getattr(request.state, "token_data", None)
    
    if not token_data:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_repo = auth_service._user_repository
    user = await user_repo.get(token_data.user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if service not in user.attrs:
        user.attrs[service] = {}
    
    user.attrs[service].update(attrs)
    user.updated_at = datetime.now(timezone.utc)
    await user_repo.set(user)
    
    return {"success": True, "service": service, "attrs": user.attrs[service]}


@router.get("/status")
async def auth_status(auth_service: AuthServiceDep):
    """Возвращает статус системы авторизации"""
    return {
        "auth_enabled": auth_service.storage is not None,
        "available_providers": [
            p.value for p in auth_service.get_available_providers()
        ],
        "total_providers": len(auth_service._providers),
    }
