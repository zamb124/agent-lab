"""
API endpoints для управления push-подписками
"""

from fastapi import APIRouter, HTTPException, Request

from core.logging import get_logger
from core.push.apns_service import get_apns_push_service
from core.push.delivery import deliver_offline_push
from core.push.schemas import SubscribeRequest, TestPushRequest, VapidPublicKeyResponse
from core.push.service import get_web_push_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/push", tags=["push"])


@router.get("/vapid-public-key", response_model=VapidPublicKeyResponse)
async def get_vapid_public_key(request: Request):
    """Получить публичный VAPID ключ для подписки"""
    push_service = get_web_push_service()

    if not push_service or not push_service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Push notifications are not configured"
        )

    return VapidPublicKeyResponse(publicKey=push_service.vapid_public_key)


@router.post("/subscribe")
async def subscribe(request: Request, body: SubscribeRequest):
    """Подписаться на push-уведомления (web_vapid или ios_apns)."""
    # Получаем user_id из сессии/токена
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        # Пробуем получить из auth
        user = getattr(request.state, 'user', None)
        if user:
            user_id = getattr(user, 'user_id', None) or getattr(user, 'id', None)

    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Получаем репозиторий из container
    container = getattr(request.app.state, 'container', None)
    if not container:
        raise HTTPException(status_code=500, detail="Container not initialized")

    push_repo = container.push_subscription_repository

    user_agent = request.headers.get('user-agent', '')[:512]

    subscription = await push_repo.upsert_subscription(
        user_id=str(user_id),
        endpoint=body.endpoint,
        keys=body.keys,
        platform=body.platform,
        user_agent=user_agent,
    )

    logger.info(
        "Push subscription upsert: user=%s transport=%s platform=%s",
        user_id,
        body.transport,
        body.platform,
    )
    return {"success": True, "subscription_id": subscription.id}


@router.delete("/unsubscribe")
async def unsubscribe(
    request: Request,
    endpoint: str
):
    """Отписаться от push-уведомлений"""
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        user = getattr(request.state, 'user', None)
        if user:
            user_id = getattr(user, 'user_id', None) or getattr(user, 'id', None)

    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    container = getattr(request.app.state, 'container', None)
    if not container:
        raise HTTPException(status_code=500, detail="Container not initialized")

    push_repo = container.push_subscription_repository

    deleted = await push_repo.delete_subscription(
        user_id=str(user_id),
        endpoint=endpoint
    )

    if deleted:
        logger.info(f"Push subscription deleted for user {user_id}")

    return {"success": True}


@router.post("/test-send")
async def test_send_push(
    request: Request,
    body: TestPushRequest
):
    """
    Отправить тестовое push-уведомление самому себе.
    Требует авторизации и наличия подписки.
    """
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        user = getattr(request.state, 'user', None)
        if user:
            user_id = getattr(user, 'user_id', None) or getattr(user, 'id', None)

    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    container = getattr(request.app.state, 'container', None)
    if not container:
        raise HTTPException(status_code=500, detail="Container not initialized")

    push_repo = container.push_subscription_repository
    web_push = get_web_push_service()
    apns = get_apns_push_service()
    if (not web_push or not web_push.is_configured) and (not apns or not apns.is_configured):
        raise HTTPException(status_code=503, detail="Push not configured")

    subscriptions = await push_repo.get_user_subscriptions(str(user_id))
    if not subscriptions:
        raise HTTPException(
            status_code=404,
            detail="No push subscriptions found. Please subscribe first.",
        )

    before = len(subscriptions)
    expired_endpoints = await deliver_offline_push(
        str(user_id),
        title=body.title,
        message=body.message,
        action_url="/dashboard",
        tag="test_notification",
        priority="normal",
        data={},
    )
    expired_count = len(expired_endpoints)
    sent_ok = before - expired_count

    logger.info(
        "Test push delivered for user %s (sent_ok=%s expired=%s)",
        user_id,
        sent_ok,
        expired_count,
    )

    return {
        "success": True,
        "sent_to_devices": sent_ok,
        "expired_subscriptions": expired_count,
    }
