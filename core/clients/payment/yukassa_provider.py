"""
Заглушка для ЮKassa провайдера.
В будущем здесь будет полная реализация через API ЮKassa.
"""

from typing import Literal, override

from pydantic import Field

from core.clients.payment.base_provider import (
    BasePaymentProvider,
    PaymentProviderConfig,
    PaymentRequest,
    PaymentResponse,
    WebhookVerificationResult,
)
from core.db.storage import Storage
from core.logging import get_logger
from core.models.payment_models import YooMoneyWebhookPayload

logger = get_logger(__name__)
YUKASSA_API_URL = "https://api.yookassa.ru/v3"


class YuKassaConfig(PaymentProviderConfig[Literal["yukassa"]]):
    """Конфигурация ЮKassa провайдера"""
    provider_type: Literal["yukassa"] = "yukassa"
    shop_id: str = Field(default="", description="ID магазина в ЮKassa")
    secret_key: str = Field(default="", description="Секретный ключ")
    api_url: str = Field(
        default=YUKASSA_API_URL,
        description="URL API ЮKassa"
    )

class YuKassaProvider(BasePaymentProvider[YuKassaConfig]):
    """
    Заглушка для ЮKassa.

    TODO: Реализовать через API:
    - Создание платежа через POST /v3/payments
    - Проверку webhook с помощью IP whitelist
    - Проверку статуса платежа через GET /v3/payments/{id}
    - Возвраты через POST /v3/refunds
    """

    def __init__(self, config: YuKassaConfig):
        super().__init__(config)
        logger.warning("ЮKassa провайдер - заглушка, не реализован")

    @override
    async def create_payment(self, request: PaymentRequest) -> PaymentResponse:
        """Заглушка: создание платежа не реализовано"""
        _ = request
        logger.error("ЮKassa провайдер не реализован")
        raise NotImplementedError("ЮKassa провайдер еще не реализован")

    @override
    async def verify_webhook(self, webhook_data: YooMoneyWebhookPayload) -> WebhookVerificationResult:
        """Заглушка: проверка webhook не реализована"""
        _ = webhook_data
        logger.error("ЮKassa провайдер не реализован")
        return WebhookVerificationResult(
            is_valid=False,
            error_message="ЮKassa провайдер не реализован"
        )

    @override
    async def check_payment_status(
        self,
        external_payment_id: str,
        storage: Storage | None = None,
    ) -> str:
        """Заглушка: проверка статуса не реализована"""
        _ = external_payment_id, storage
        logger.error("ЮKassa провайдер не реализован")
        return "unknown"

    @override
    async def refund_payment(self, external_payment_id: str, amount: float) -> bool:
        """Заглушка: возврат не реализован"""
        _ = external_payment_id, amount
        logger.error("ЮKassa провайдер не реализован")
        return False
