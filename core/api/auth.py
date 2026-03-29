"""
API эндпоинты для авторизации.

Общий роутер для авторизации, может использоваться в любом сервисе.
Контейнер получается через request.app.state.container.
"""

import logging
from typing import Annotated, Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from core.config import get_settings
from core.models import AuthProvider, AuthRequest
from core.identity import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


class UserUpdate(BaseModel):
    """Обновление данных пользователя"""
    name: Optional[str] = None
    emails: Optional[List[str]] = None
    phones: Optional[List[str]] = None
    messengers: Optional[Dict[str, str]] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    ui_preferences: Optional[Dict[str, Any]] = None


def get_auth_service(request: Request) -> AuthService:
    """Получает AuthService из контейнера приложения"""
    return request.app.state.container.auth_service


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


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


@router.get("/callback/{provider_name}")
async def auth_callback(
    request: Request,
    provider_name: str,
    code: str,
    state: str,
    auth_service: AuthServiceDep,
    error: str = None,
):
    """
    Обрабатывает callback от провайдера авторизации.

    Args:
        provider_name: Имя провайдера
        code: Код авторизации от провайдера
        state: State для CSRF защиты
        error: Ошибка от провайдера (если есть)
    """
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

    # Получаем state с оригинальным хостом и redirect_uri
    auth_state = await auth_service._get_auth_state(state)
    if not auth_state:
        raise HTTPException(status_code=400, detail="Недействительный state")
    
    original_host = auth_state.get("original_host")
    redirect_uri = auth_state.get("redirect_uri")

    logger.info(f"auth_callback: redirect_uri={redirect_uri}, original_host={original_host}")

    auth_request = AuthRequest(
        provider=provider, code=code, state=state, redirect_uri=redirect_uri
    )

    result = await auth_service.complete_auth(auth_request)
    
    logger.info(f"Результат авторизации: success={result.success}, error={result.error_message}")

    if not result.success:
        logger.error(f"Ошибка завершения авторизации: {result.error_message}")
        raise HTTPException(status_code=400, detail=result.error_message)

    # Используем оригинальный хост для редиректа
    target_host = original_host or request.headers.get("host", "")
    
    response = RedirectResponse(url="/select-company")
    is_production = settings.server.env == "production"
    
    cookie_domain = get_cookie_domain(target_host)

    logger.info(f"Устанавливаем cookies: session_id={result.session.session_id}, auth_token={result.token[:8]}..., domain={cookie_domain}, secure={is_production}")

    response.set_cookie(
        key="session_id",
        value=result.session.session_id,
        domain=cookie_domain,
        httponly=True,
        secure=is_production,
        samesite="lax",
    )
    response.set_cookie(
        key="auth_token",
        value=result.token,
        domain=cookie_domain,
        httponly=False,
        secure=is_production,
        samesite="lax",
    )

    logger.info(f"Успешная авторизация пользователя {result.user.user_id}")
    return response


@router.post("/logout")
async def logout(session_id: str, auth_service: AuthServiceDep):
    """
    Завершает сессию пользователя.

    Args:
        session_id: ID сессии для завершения
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="Не указан session_id")

    success = await auth_service.logout(session_id)

    if success:
        return {"success": True, "message": "Сессия завершена"}
    else:
        raise HTTPException(status_code=500, detail="Ошибка завершения сессии")


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
