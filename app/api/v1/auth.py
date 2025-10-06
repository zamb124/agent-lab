"""
API эндпоинты для авторизации.
"""

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from app.core.config import settings

from app.identity.auth_service import auth_service
from app.identity.models import AuthProvider, AuthRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/providers")
async def get_auth_providers():
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
async def start_auth(provider_name: str, redirect_uri: str = None):
    """
    Начинает процесс авторизации с выбранным провайдером.

    Args:
        provider_name: Имя провайдера (yandex, google, etc.)
        redirect_uri: URI для возврата после авторизации
    """
    try:
        provider = AuthProvider(provider_name)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Неподдерживаемый провайдер: {provider_name}"
        )

    # Формируем правильный redirect_uri если не передан
    if redirect_uri is None:
        redirect_uri = f"https://agents-lab.ru/auth/callback/{provider_name}"

    try:
        auth_url = await auth_service.start_auth(provider, redirect_uri)
        return RedirectResponse(url=auth_url)
    except Exception as e:
        logger.error(f"Ошибка начала авторизации {provider_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/callback/{provider_name}")
async def auth_callback(
    provider_name: str,
    code: str,
    state: str,
    error: str = None,
    redirect_uri: str = None,
):
    """
    Обрабатывает callback от провайдера авторизации.

    Args:
        provider_name: Имя провайдера
        code: Код авторизации от провайдера
        state: State для CSRF защиты
        error: Ошибка от провайдера (если есть)
        redirect_uri: URI callback
    """
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

    # Формируем правильный redirect_uri если не передан
    if redirect_uri is None:
        redirect_uri = f"https://agents-lab.ru/auth/callback/{provider_name}"

    # Формируем запрос авторизации
    auth_request = AuthRequest(
        provider=provider, code=code, state=state, redirect_uri=redirect_uri
    )

    # Завершаем авторизацию
    result = await auth_service.complete_auth(auth_request)

    if not result.success:
        logger.error(f"Ошибка завершения авторизации: {result.error_message}")
        raise HTTPException(status_code=400, detail=result.error_message)

    # Устанавливаем сессию в cookies и перенаправляем на dashboard
    response = RedirectResponse(url="/frontend/dashboard")
    # Настройки куки в зависимости от окружения
    is_production = settings.server.env == "production"
    
    # Для локальной разработки НЕ устанавливаем домен - куки будут работать везде
    if settings.server.env == "local":
        domain = None
    else:
        domain = f".{settings.server.domain}"
    
    response.set_cookie(
        key="session_id",
        value=result.session.session_id,
        domain=domain,
        httponly=True,
        secure=is_production,
        samesite="lax",
    )
    response.set_cookie(
        key="auth_token",
        value=result.session.session_id,  # Используем session_id как auth_token
        domain=domain,
        httponly=False,  # Нужно для JS
        secure=is_production,
        samesite="lax",
    )

    logger.info(f"✅ Успешная авторизация пользователя {result.user.user_id}")
    return response


@router.get("/me")
async def get_current_user(session_id: str = None):
    """
    Возвращает информацию о текущем пользователе.

    Args:
        session_id: ID сессии (можно передать в query или cookie)
    """
    if not session_id:
        raise HTTPException(status_code=401, detail="Не авторизован")

    user = await auth_service.get_user_by_session(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Сессия недействительна")
    
    session = await auth_service._get_session(session_id)
    provider_value = session.provider.value if session else None
    
    email = None
    avatar_url = None
    if session:
        provider_info = await auth_service.get_user_provider_info(user.user_id, session.provider)
        if provider_info:
            email = provider_info.get("email")
            avatar_url = provider_info.get("avatar_url")

    return {
        "user_id": user.user_id,
        "email": email,
        "name": user.name,
        "avatar_url": avatar_url,
        "provider": provider_value,
        "status": user.status.value,
    }


@router.post("/logout")
async def logout(session_id: str):
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


@router.get("/status")
async def auth_status():
    """Возвращает статус системы авторизации"""
    return {
        "auth_enabled": auth_service.storage is not None,
        "available_providers": [
            p.value for p in auth_service.get_available_providers()
        ],
        "total_providers": len(auth_service._providers),
    }
