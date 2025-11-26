"""
API эндпоинты для авторизации.

Общий роутер для авторизации, может использоваться в любом сервисе.
"""

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from core.config import get_settings
from core.container import get_system_container
from core.models import AuthProvider, AuthRequest

logger = logging.getLogger(__name__)

router = APIRouter()


def get_auth_service():
    """Получает AuthService из системного контейнера"""
    return get_system_container().auth_service


@router.get("/providers")
async def get_auth_providers():
    """Возвращает список доступных провайдеров авторизации"""
    providers = get_auth_service().get_available_providers()

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
    settings = get_settings()
    
    try:
        provider = AuthProvider(provider_name)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Неподдерживаемый провайдер: {provider_name}"
        )

    if redirect_uri is None:
        redirect_uri = f"https://{settings.server.domain}/auth/callback/{provider_name}"
    
    logger.info(f"start_auth: env={settings.server.env}, redirect_uri={redirect_uri}")

    try:
        auth_url = await get_auth_service().start_auth(provider, redirect_uri)
        return RedirectResponse(url=auth_url)
    except Exception as e:
        logger.error(f"Ошибка начала авторизации {provider_name}: {e}", exc_info=True)
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

    if redirect_uri is None:
        redirect_uri = f"https://{settings.server.domain}/auth/callback/{provider_name}"

    logger.info(f"auth_callback: env={settings.server.env}, redirect_uri={redirect_uri}")

    auth_request = AuthRequest(
        provider=provider, code=code, state=state, redirect_uri=redirect_uri
    )

    result = await get_auth_service().complete_auth(auth_request)
    
    logger.info(f"Результат авторизации: success={result.success}, error={result.error_message}")

    if not result.success:
        logger.error(f"Ошибка завершения авторизации: {result.error_message}")
        raise HTTPException(status_code=400, detail=result.error_message)

    response = RedirectResponse(url="/frontend/select-company")
    is_production = settings.server.env == "production"
    domain = None if settings.server.env == "local" else f".{settings.server.domain}"

    logger.info(f"Устанавливаем cookies: session_id={result.session.session_id}, auth_token={result.token[:8]}..., domain={domain}, secure={is_production}")

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
        value=result.token,
        domain=domain,
        httponly=False,
        secure=is_production,
        samesite="lax",
    )

    logger.info(f"Успешная авторизация пользователя {result.user.user_id}")
    return response


@router.post("/logout")
async def logout(session_id: str):
    """
    Завершает сессию пользователя.

    Args:
        session_id: ID сессии для завершения
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="Не указан session_id")

    success = await get_auth_service().logout(session_id)

    if success:
        return {"success": True, "message": "Сессия завершена"}
    else:
        raise HTTPException(status_code=500, detail="Ошибка завершения сессии")


@router.get("/status")
async def auth_status():
    """Возвращает статус системы авторизации"""
    return {
        "auth_enabled": get_auth_service().storage is not None,
        "available_providers": [
            p.value for p in get_auth_service().get_available_providers()
        ],
        "total_providers": len(get_auth_service()._providers),
    }

