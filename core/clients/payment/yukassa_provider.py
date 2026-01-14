"""
Заглушка для ЮKassa провайдера.
В будущем здесь будет полная реализация через API ЮKassa.
"""

import logging
from typing import Dict, Any, Literal
from pydantic import Field

from core.clients.payment.base_provider import (
    BasePaymentProvider,
    PaymentProviderConfig,
    PaymentRequest,
    PaymentResponse,
    WebhookVerificationResult
)

logger = logging.getLogger(__name__)


class YuKassaConfig(PaymentProviderConfig):
    """Конфигурация ЮKassa провайдера"""
    provider_type: Literal["yukassa"] = "yukassa"
    shop_id: str = Field(default="", description="ID магазина в ЮKassa")
    secret_key: str = Field(default="", description="Секретный ключ")
    api_url: str = Field(
        default="https://api.yookassa.ru/v3",
        description="URL API ЮKassa"
    )


class YuKassaProvider(BasePaymentProvider):
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
        self.config: YuKassaConfig = config
        logger.warning("ЮKassa провайдер - заглушка, не реализован")
    
    async def create_payment(self, request: PaymentRequest) -> PaymentResponse:
        """Заглушка: создание платежа не реализовано"""
        logger.error("ЮKassa провайдер не реализован")
        raise NotImplementedError("ЮKassa провайдер еще не реализован")
    
    async def verify_webhook(self, webhook_data: Dict[str, Any]) -> WebhookVerificationResult:
        """Заглушка: проверка webhook не реализована"""
        logger.error("ЮKassa провайдер не реализован")
        return WebhookVerificationResult(
            is_valid=False,
            error_message="ЮKassa провайдер не реализован"
        )
    
    async def check_payment_status(self, external_payment_id: str) -> str:
        """Заглушка: проверка статуса не реализована"""
        logger.error("ЮKassa провайдер не реализован")
        return "unknown"
    
    async def refund_payment(self, external_payment_id: str, amount: float) -> bool:
        """Заглушка: возврат не реализован"""
        logger.error("ЮKassa провайдер не реализован")
        return False








