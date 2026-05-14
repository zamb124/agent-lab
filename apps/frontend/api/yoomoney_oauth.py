"""
OAuth endpoints для YooMoney: авторизация и callback.

GET /api/billing/yoomoney/authorize — формирует URL авторизации YooMoney
GET /api/billing/yoomoney/callback — обменивает code на access_token
"""

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from apps.frontend.dependencies import ContainerDep
from core.clients.payment.factory import PaymentProviderFactory
from core.clients.payment.yoomoney_provider import (
    YOOMONEY_OAUTH_AUTHORIZE_URL,
    YOOMONEY_OAUTH_TOKEN_URL,
    YooMoneyProvider,
    save_access_token,
)
from core.http import request_public_oauth
from core.logging import get_logger
from core.utils.domain import PRIMARY_DOMAIN

logger = get_logger(__name__)
router = APIRouter(prefix="/api/billing/yoomoney", tags=["yoomoney-oauth"])

def _get_yoomoney_provider() -> YooMoneyProvider:
    """Возвращает активный YooMoney провайдер."""
    for name, provider in PaymentProviderFactory.get_available_providers().items():
        if isinstance(provider, YooMoneyProvider):
            return provider
    raise HTTPException(status_code=503, detail="YooMoney провайдер не настроен")

def _build_callback_url(request: Request) -> str:
    """Формирует абсолютный URL для OAuth callback на apex-домене."""
    from core.config import get_settings
    settings = get_settings()

    if settings.server.env == "local":
        host = request.headers.get("host", f"localhost:{settings.server.port}")
        return f"http://{host}/frontend/api/billing/yoomoney/callback"

    return f"https://{PRIMARY_DOMAIN}/frontend/api/billing/yoomoney/callback"

@router.get("/authorize")
async def yoomoney_authorize(request: Request, container: ContainerDep):
    """
    Формирует URL авторизации YooMoney и возвращает его.
    Только owner/admin.
    """
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    if not hasattr(request.state, "company") or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")

    user = request.state.user
    company = request.state.company

    user_roles = company.members.get(user.user_id, [])
    if "owner" not in user_roles and "admin" not in user_roles:
        raise HTTPException(status_code=403, detail="Только owner или admin может авторизовать YooMoney")

    provider = _get_yoomoney_provider()

    if not provider.config.client_id:
        raise HTTPException(status_code=503, detail="client_id не настроен для YooMoney")

    redirect_uri = _build_callback_url(request)

    params = {
        "client_id": provider.config.client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": "account-info operation-history operation-details",
    }

    logger.info(
        "YooMoney OAuth: пользователь %s инициировал авторизацию, redirect_uri=%s",
        user.user_id, redirect_uri,
    )

    authorize_url = f"{YOOMONEY_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"
    return JSONResponse(content={"authorize_url": authorize_url})

@router.get("/callback")
async def yoomoney_callback(request: Request, container: ContainerDep, code: str = ""):
    """
    Принимает code от YooMoney, обменивает на access_token.
    Endpoint без JWT-авторизации (YooMoney делает redirect).
    """
    if not code:
        raise HTTPException(status_code=400, detail="Параметр code обязателен")

    provider = _get_yoomoney_provider()

    if not provider.config.client_id or not provider.config.client_secret:
        raise HTTPException(status_code=503, detail="client_id/client_secret не настроены")

    redirect_uri = _build_callback_url(request)

    response = await request_public_oauth(
        "post",
        YOOMONEY_OAUTH_TOKEN_URL,
        data={
            "code": code,
            "client_id": provider.config.client_id,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "client_secret": provider.config.client_secret,
        },
    )
    response.raise_for_status()

    token_response = response.json()
    access_token = token_response.get("access_token")
    if not access_token:
        error = token_response.get("error", "unknown")
        logger.error("YooMoney OAuth: не удалось получить access_token: %s", token_response)
        raise HTTPException(status_code=502, detail=f"YooMoney вернул ошибку: {error}")

    storage = container.company_repository._storage
    await save_access_token(storage, access_token)

    provider._access_token = access_token

    logger.info("YooMoney OAuth: access_token успешно получен и сохранён")

    return RedirectResponse(url="/billing?oauth=success")
