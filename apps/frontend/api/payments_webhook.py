"""
Webhook для приёма уведомлений от платежных провайдеров (YooMoney).

Два эквивалентных пути (см. `apps/frontend/main.py`):

- `https://<host>/api/v1/payments/webhook/<provider_name>` — то, что обычно задают у провайдера
- `https://<host>/frontend/api/v1/payments/webhook/<provider_name>` — вместе с префиксом сервиса

YooMoney отправляет POST application/x-www-form-urlencoded,
ожидает HTTP 200 OK в ответ.
"""


from fastapi import APIRouter, Form, HTTPException, Response

from apps.frontend.dependencies import ContainerDep
from core.clients.payment import PaymentProviderFactory
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/payments", tags=["payments-webhook"])

@router.post("/webhook/{provider_name}")
async def payment_webhook(
    provider_name: str,
    container: ContainerDep,
    notification_type: str = Form(""),
    operation_id: str = Form(""),
    amount: str = Form(""),
    currency: str = Form(""),
    datetime: str = Form(""),
    sender: str = Form(""),
    codepro: str = Form(""),
    sha1_hash: str = Form(""),
    label: str = Form(""),
    test_notification: str | None = Form(None),
):
    logger.info(
        "Webhook %s: label=%s, amount=%s, operation_id=%s",
        provider_name, label, amount, operation_id,
    )

    provider = PaymentProviderFactory.get_provider(provider_name)
    if not provider:
        logger.error("Провайдер %s не найден", provider_name)
        raise HTTPException(status_code=404, detail=f"Провайдер {provider_name} не найден")

    webhook_data: JsonObject = {
        "notification_type": notification_type,
        "operation_id": operation_id,
        "amount": amount,
        "currency": currency,
        "datetime": datetime,
        "sender": sender,
        "codepro": codepro,
        "sha1_hash": sha1_hash,
        "label": label,
    }

    if test_notification:
        webhook_data["test_notification"] = test_notification

    verification = await provider.verify_webhook(webhook_data)

    if not verification.is_valid:
        logger.warning(
            "Невалидный webhook от %s: %s", provider_name, verification.error_message,
        )
        return Response(status_code=200)

    await container.payment_service.process_webhook(
        verification_result=verification,
        provider_name=provider_name,
        raw_data=webhook_data,
    )

    return Response(status_code=200)
