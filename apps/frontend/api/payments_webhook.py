"""
Webhook для приёма уведомлений от Т-Банка (JSON NotificationPayment).

Два эквивалентных пути (см. `apps/frontend/main.py`):

- `https://<host>/api/v1/payments/webhook/<provider_name>`
- `https://<host>/frontend/api/v1/payments/webhook/<provider_name>`

Т-Банк отправляет POST application/json и ожидает HTTP 200 с телом `OK`.
Неизвестный OrderId и неверный Token — тоже 200 `OK`, без зачисления:
иначе банк ретраит час/сутки/месяц.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from apps.frontend.di import Di
from core.clients.payment import PaymentProviderFactory
from core.logging import get_logger
from core.models.payment_models import TinkoffNotificationPayload
from core.types import parse_json_object

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/payments", tags=["payments-webhook"])


@router.post("/webhook/{provider_name}")
async def payment_webhook(
    provider_name: str,
    di: Di,
    request: Request,
) -> PlainTextResponse:
    try:
        raw_body = parse_json_object(await request.body(), "Tinkoff webhook")
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Tinkoff webhook must be a JSON object"
        ) from exc
    logger.info(
        "payments.webhook_received",
        provider=provider_name,
        order_id=raw_body.get("OrderId"),
        status=raw_body.get("Status"),
        payment_id=raw_body.get("PaymentId"),
    )

    provider = PaymentProviderFactory.get_provider(provider_name)
    if not provider:
        logger.error("payments.webhook_provider_missing", provider=provider_name)
        raise HTTPException(status_code=404, detail=f"Provider {provider_name} not found")

    verification = await provider.verify_webhook(raw_body)

    if not verification.is_valid:
        logger.warning(
            "payments.webhook_invalid",
            provider=provider_name,
            error=verification.error_message,
        )
        return PlainTextResponse("OK")

    webhook_payload = TinkoffNotificationPayload.model_validate(raw_body)
    await di.payment_service.process_webhook(
        verification_result=verification,
        provider_name=provider_name,
        raw_data=webhook_payload,
    )

    return PlainTextResponse("OK")
