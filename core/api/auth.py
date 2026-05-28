"""
API эндпоинты для авторизации.

Общий роутер для авторизации, может использоваться в любом сервисе.
Контейнер получается через request.app.state.container.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Annotated
from typing import cast as type_cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel
from pydantic import Field as PydanticField

from core.app_state import PlatformAppState
from core.config import get_settings
from core.identity import AuthService
from core.logging import get_logger
from core.models import AuthProvider, AuthRequest
from core.types import JsonObject, require_json_object
from core.utils.domain import build_url, get_cookie_domain, get_host_with_port, is_local
from core.utils.tokens import TokenData, TokenService, get_token_service

logger = get_logger(__name__)
router = APIRouter(tags=["auth"])

if TYPE_CHECKING:
    from core.container import BaseContainer


class UserUpdate(BaseModel):
    """Обновление данных пользователя"""

    name: str | None = PydanticField(None, max_length=200)
    first_name: str | None = PydanticField(None, max_length=100)
    last_name: str | None = PydanticField(None, max_length=100)
    emails: list[str] | None = None
    phones: list[str] | None = None
    messengers: dict[str, str] | None = None
    avatar_url: str | None = None
    bio: str | None = PydanticField(None, max_length=4000)
    ui_preferences: JsonObject | None = None


class SwitchCompanyRequest(BaseModel):
    """Переключение активной компании пользователя"""

    company_id: str


class DemoLoginRequest(BaseModel):
    email: str
    password: str


def get_auth_service(request: Request) -> AuthService:
    """Получает AuthService из контейнера приложения"""
    return _auth_container(request).auth_service


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def _platform_app_state(request: Request) -> PlatformAppState:
    app = type_cast(FastAPI, request.app)
    if not hasattr(app.state, "container") or not hasattr(app.state, "settings"):
        raise RuntimeError("Platform app state is not configured")
    return type_cast(PlatformAppState, type_cast(object, app.state))


def _auth_container(request: Request) -> BaseContainer:
    return _platform_app_state(request).container


def _oauth_callback_container(request: Request) -> BaseContainer:
    return _platform_app_state(request).container


def _request_token_data(request: Request) -> TokenData | None:
    token_data = getattr(request.state, "token_data", None)
    if token_data is None:
        return None
    if not isinstance(token_data, TokenData):
        raise RuntimeError("AuthMiddleware did not populate request.state.token_data")
    return token_data


def _require_token_data(request: Request) -> TokenData:
    token_data = _request_token_data(request)
    if token_data is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return token_data


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


def _append_query(url: str, params: dict[str, str]) -> str:
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
        "/dashboard?post_login=1",
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
    redirect_uri: str | None = None,
    return_path: str | None = None,
):
    """
    Начинает процесс авторизации с выбранным провайдером.

    Аргументы:
        request: FastAPI request для определения redirect_uri
        provider_name: Имя провайдера (yandex, google, etc.)
        redirect_uri: URI для возврата после авторизации (опционально)

    Возвращает:
        JSON с auth_url для редиректа на стороне клиента
    """
    try:
        provider = AuthProvider(provider_name)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Неподдерживаемый провайдер: {provider_name}")

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
    code: str | None,
    state: str | None,
    auth_service: AuthService,
    error: str | None = None,
    oauth_first_login_user_json: str | None = None,
) -> RedirectResponse:
    """Общая логика GET/POST callback (Apple form_post передаёт поля в теле формы)."""
    settings = get_settings()

    if error:
        logger.error(f"Ошибка авторизации от {provider_name}: {error}")
        raise HTTPException(status_code=400, detail=f"Ошибка авторизации: {error}")

    if not code or not state:
        raise HTTPException(status_code=400, detail="Отсутствуют обязательные параметры")

    try:
        provider = AuthProvider(provider_name)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Неподдерживаемый провайдер: {provider_name}")

    auth_state = await auth_service.get_auth_state(state)
    if not auth_state:
        if provider_name == AuthProvider.GOOGLE.value:
            calendar_service = _oauth_callback_container(request).calendar_service
            try:
                return_path = await calendar_service.complete_google_oauth(state=state, code=code)
            except ValueError as err:
                raise HTTPException(status_code=400, detail=str(err)) from err
            redirect_url = _append_query(
                return_path,
                {
                    "integration_provider": "google",
                    "integration_service": "calendar",
                    "integration_status": "connected",
                },
            )
            return RedirectResponse(url=redirect_url)
        raise HTTPException(status_code=400, detail="Недействительный state")

    original_host = auth_state.original_host
    redirect_uri = auth_state.redirect_uri
    return_path = auth_state.return_path

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
    if result.user is None or result.session is None or result.token is None:
        raise HTTPException(status_code=500, detail="Некорректный результат авторизации")
    user = result.user
    session = result.session
    token = result.token

    target_host = original_host or request.headers.get("host", "")
    if return_path:
        if not return_path.startswith("/"):
            raise HTTPException(status_code=400, detail="Некорректный return_path")
        redirect_url = build_url(target_host, return_path)
    elif not user.companies or len(user.companies) == 0:
        redirect_url = build_url(target_host, "/select-company?action=create")
    elif len(user.companies) == 1:
        company_id = list(user.companies.keys())[0]
        company = await auth_service.get_company(company_id)
        if not company or not company.subdomain:
            redirect_url = build_url(target_host, "/select-company?action=create")
        else:
            redirect_url = build_url(target_host, "/dashboard?post_login=1", company.subdomain)
    else:
        active_company_id = user.active_company_id
        if active_company_id and active_company_id in user.companies:
            company = await auth_service.get_company(active_company_id)
            if company and company.subdomain:
                redirect_url = build_url(target_host, "/dashboard?post_login=1", company.subdomain)
            else:
                redirect_url = build_url(target_host, "/select-company")
        else:
            redirect_url = build_url(target_host, "/select-company")

    response = RedirectResponse(url=redirect_url)
    is_production = settings.server.env == "production"

    cookie_domain = get_cookie_domain(target_host)

    logger.info(
        f"Устанавливаем cookies: session_id={session.session_id}, auth_token={token[:8]}..., domain={cookie_domain}, secure={is_production}"
    )

    cookie_max_age = TokenService.SESSION_EXPIRES
    response.set_cookie(
        key="session_id",
        value=session.session_id,
        domain=cookie_domain,
        httponly=True,
        secure=is_production,
        samesite="lax",
        max_age=cookie_max_age,
    )
    response.set_cookie(
        key="auth_token",
        value=token,
        domain=cookie_domain,
        httponly=False,
        secure=is_production,
        samesite="lax",
        max_age=cookie_max_age,
    )

    logger.info(f"Успешная авторизация пользователя {user.user_id}")
    return response


@router.get("/callback/{provider_name}")
async def auth_callback(
    request: Request,
    provider_name: str,
    code: str,
    state: str,
    auth_service: AuthServiceDep,
    error: str | None = None,
    user: str | None = None,
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
    code: Annotated[str, Form()],
    state: Annotated[str, Form()],
    error: Annotated[str | None, Form()] = None,
    user: Annotated[str | None, Form()] = None,
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
    session_id: Annotated[str | None, Query()] = None,
):
    """
    Завершает сессию: берёт session_id из query (опционально) или из JWT в cookie,
    удаляет запись сессии и снимает auth_token/session_id в браузере.
    """
    token_data = _request_token_data(request)
    resolved_session_id = session_id
    if resolved_session_id is None and token_data is not None:
        resolved_session_id = token_data.session_id
    if resolved_session_id is not None:
        _ = await auth_service.logout(resolved_session_id)

    response = JSONResponse({"success": True, "message": "Сессия завершена"})
    _clear_platform_auth_cookies(response, request)
    return response


@router.get("/me")
async def get_current_user(request: Request, auth_service: AuthServiceDep):
    """
    Возвращает полную информацию о текущем авторизованном пользователе.
    """
    token_data = _require_token_data(request)

    user = await auth_service.get_user(token_data.user_id)

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
        "attrs": user.attributes,
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
    token_data = _require_token_data(request)

    user = await auth_service.get_user(token_data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.company_id not in user.companies:
        raise HTTPException(status_code=403, detail="Нет доступа к выбранной компании")

    user.active_company_id = payload.company_id
    _ = await auth_service.save_user(user)

    company_roles = user.companies[payload.company_id]
    token_service = get_token_service()
    issued_token = token_service.create_token(
        user_id=user.user_id,
        company_id=payload.company_id,
        roles=company_roles,
        session_id=token_data.session_id,
        email=user.email,
    )

    settings = get_settings()
    response = JSONResponse(content={"success": True, "company_id": payload.company_id})
    response.set_cookie(
        key="auth_token",
        value=issued_token,
        domain=get_cookie_domain(request.headers.get("host", "")),
        httponly=True,
        secure=settings.server.env == "production",
        samesite="lax",
        max_age=TokenService.SESSION_EXPIRES,
    )
    return response


@router.put("/me")
async def update_current_user(
    request: Request, updates: "UserUpdate", auth_service: AuthServiceDep
):
    """
    Обновляет данные текущего пользователя.
    """
    token_data = _require_token_data(request)

    user = await auth_service.get_user(token_data.user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    name_parts_changed = False
    if updates.name is not None:
        user.name = updates.name
    if updates.first_name is not None:
        user.first_name = updates.first_name
        name_parts_changed = True
    if updates.last_name is not None:
        user.last_name = updates.last_name
        name_parts_changed = True
    if updates.emails is not None:
        user.emails = updates.emails
    if updates.phones is not None:
        user.phones = updates.phones
    if updates.messengers is not None:
        user.messengers = updates.messengers
    if updates.avatar_url is not None:
        user.avatar_url = updates.avatar_url
    if updates.bio is not None:
        user.bio = updates.bio
    if updates.ui_preferences is not None:
        user.ui_preferences = updates.ui_preferences

    if name_parts_changed:
        parts: list[str] = []
        if user.first_name and user.first_name.strip():
            parts.append(user.first_name.strip())
        if user.last_name and user.last_name.strip():
            parts.append(user.last_name.strip())
        if parts:
            user.name = " ".join(parts)

    user.updated_at = datetime.now(timezone.utc)
    _ = await auth_service.save_user(user)

    return {"success": True, "message": "User updated"}


@router.get("/me/attrs/{service}")
async def get_service_attrs(
    request: Request, service: str, auth_service: AuthServiceDep
) -> JsonObject:
    """
    Получает service-specific атрибуты для текущего пользователя.

    Аргументы:
        service: Имя сервиса (crm, agents, rag)
    """
    token_data = _require_token_data(request)

    user = await auth_service.get_user(token_data.user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    service_attrs = user.attributes.get(service)
    if service_attrs is None:
        return {}
    return require_json_object(service_attrs, f"user.attributes[{service!r}]")


@router.put("/me/attrs/{service}")
async def update_service_attrs(
    request: Request, service: str, attrs: JsonObject, auth_service: AuthServiceDep
) -> JsonObject:
    """
    Обновляет service-specific атрибуты для текущего пользователя (merge).

    Аргументы:
        service: Имя сервиса (crm, agents, rag)
        attrs: Атрибуты для обновления (merge с существующими)
    """
    token_data = _require_token_data(request)

    user = await auth_service.get_user(token_data.user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    existing_attrs = user.attributes.get(service)
    if existing_attrs is None:
        service_attrs: JsonObject = {}
    else:
        service_attrs = require_json_object(existing_attrs, f"user.attributes[{service!r}]")

    user.attributes[service] = {**service_attrs, **attrs}
    user.updated_at = datetime.now(timezone.utc)
    _ = await auth_service.save_user(user)

    return {"success": True, "service": service, "attrs": user.attributes[service]}


@router.get("/grafana-check")
async def grafana_auth_check(request: Request):
    """
    Проверка доступа к Grafana: только пользователи company_id == 'system'.

    Вызывается Traefik ForwardAuth (Middleware на Ingress grafana), не браузером напрямую.
    AuthMiddleware уже отработал к моменту вызова и положил token_data в request.state.

    При успехе возвращает 200 + заголовок X-Auth-User (email или user_id), который Traefik
    пробрасывает в Grafana как auth.proxy (GF_AUTH_PROXY_HEADER_NAME).
    """
    token_data = _request_token_data(request)
    if token_data is None:
        return Response(status_code=401)

    if token_data.company_id != "system":
        return Response(status_code=403)

    user_email = token_data.email
    if not user_email:
        user_email = token_data.user_id
    return Response(
        status_code=200,
        headers={"X-Auth-User": str(user_email)},
    )


@router.get("/status")
async def auth_status(auth_service: AuthServiceDep):
    """Возвращает статус системы авторизации"""
    return {
        "auth_enabled": auth_service.storage_configured,
        "available_providers": [p.value for p in auth_service.get_available_providers()],
        "total_providers": auth_service.provider_count,
    }
