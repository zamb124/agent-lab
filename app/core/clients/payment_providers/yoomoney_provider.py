"""
Провайдер для приема платежей через YooMoney (ЮMoney).
Использует Quickpay форму для приема платежей.
"""

import hashlib
import logging
from urllib.parse import urlencode
from typing import Dict, Any, Optional, Literal
from pydantic import Field

from .base_provider import (
    BasePaymentProvider,
    PaymentProviderConfig,
    PaymentRequest,
    PaymentResponse,
    WebhookVerificationResult
)

logger = logging.getLogger(__name__)


class YooMoneyConfig(PaymentProviderConfig):
    """Конфигурация YooMoney провайдера"""
    provider_type: Literal["yoomoney"] = "yoomoney"
    account_number: str = Field(description="Номер кошелька YooMoney")
    notification_secret: str = Field(description="Секрет для проверки HTTP-уведомлений")
    quickpay_url: str = Field(
        default="https://yoomoney.ru/quickpay/confirm.xml",
        description="URL формы оплаты Quickpay"
    )
    client_id: Optional[str] = Field(default=None, description="OAuth client_id приложения (для API кошелька в будущем)")
    client_secret: Optional[str] = Field(default=None, description="OAuth client_secret приложения (для API кошелька в будущем)")


class YooMoneyProvider(BasePaymentProvider):
    """
    Провайдер для YooMoney (Quickpay).
    
    Документация: https://yoomoney.ru/docs/wallet
    """
    
    def __init__(self, config: YooMoneyConfig):
        super().__init__(config)
        self.config: YooMoneyConfig = config
        logger.info(f"Инициализирован YooMoney провайдер: кошелек={config.account_number}")
    
    async def create_payment(self, request: PaymentRequest) -> PaymentResponse:
        """
        Генерирует URL для YooMoney Quickpay формы.
        
        Документация: https://yoomoney.ru/docs/payment-buttons/using-api/forms
        """
        
        logger.info(
            f"Создание платежа YooMoney: сумма={request.amount}₽, "
            f"компания={request.company_id}, транзакция={request.transaction_id}"
        )
        
        params = {
            "receiver": self.config.account_number,
            "quickpay-form": "shop",
            "targets": f"Пополнение баланса (ID: {request.transaction_id})",
            "paymentType": "AC",
            "sum": str(request.amount),
            "label": request.transaction_id,
            "successURL": request.success_url,
            "failURL": request.fail_url
        }
        
        payment_url = f"{self.config.quickpay_url}?{urlencode(params)}"
        
        logger.debug(f"Сгенерирован URL платежа: {payment_url}")
        
        return PaymentResponse(
            payment_url=payment_url,
            external_payment_id=None,
            metadata={
                "provider": "yoomoney",
                "account_number": self.config.account_number
            }
        )
    
    async def verify_webhook(self, webhook_data: Dict[str, Any]) -> WebhookVerificationResult:
        """
        Проверяет подпись YooMoney HTTP-уведомления.
        
        Формат подписи:
        sha1(notification_type&operation_id&amount&currency&datetime&sender&codepro&notification_secret&label)
        
        Документация: https://yoomoney.ru/docs/wallet/using-api/notification-p2p-incoming
        """
        
        logger.info("Проверка YooMoney webhook")
        
        notification_type = webhook_data.get("notification_type")
        operation_id = webhook_data.get("operation_id")
        amount = webhook_data.get("withdraw_amount") or webhook_data.get("amount")
        currency = webhook_data.get("currency", "643")
        datetime_str = webhook_data.get("datetime")
        sender = webhook_data.get("sender")
        codepro = webhook_data.get("codepro", "false")
        label = webhook_data.get("label")
        received_hash = webhook_data.get("sha1_hash")
        
        if not all([notification_type, operation_id, amount, datetime_str, sender, label, received_hash]):
            logger.error("Отсутствуют обязательные поля в webhook")
            return WebhookVerificationResult(
                is_valid=False,
                error_message="Missing required fields"
            )
        
        check_string = (
            f"{notification_type}&{operation_id}&{amount}&{currency}&"
            f"{datetime_str}&{sender}&{codepro}&{self.config.notification_secret}&{label}"
        )
        
        calculated_hash = hashlib.sha1(check_string.encode('utf-8')).hexdigest()
        
        if calculated_hash != received_hash:
            logger.error(
                f"Неверная подпись webhook: ожидалось={calculated_hash}, "
                f"получено={received_hash}"
            )
            return WebhookVerificationResult(
                is_valid=False,
                error_message="Invalid signature"
            )
        
        logger.info(
            f"Webhook проверен успешно: транзакция={label}, "
            f"сумма={amount}₽, operation_id={operation_id}"
        )
        
        return WebhookVerificationResult(
            is_valid=True,
            transaction_id=label,
            amount=float(amount),
            external_payment_id=operation_id,
            status="success"
        )
    
    async def check_payment_status(self, external_payment_id: str) -> str:
        """
        YooMoney Quickpay не предоставляет API для проверки статуса платежа.
        Статус известен только через HTTP-уведомления.
        """
        logger.warning(
            f"YooMoney Quickpay не поддерживает проверку статуса. "
            f"Используйте только HTTP-уведомления."
        )
        return "unknown"
    
    async def refund_payment(self, external_payment_id: str, amount: float) -> bool:
        """
        YooMoney Quickpay не поддерживает автоматические возвраты через API.
        Требуется ручная обработка возвратов.
        """
        logger.warning(
            f"YooMoney Quickpay не поддерживает автоматические возвраты. "
            f"operation_id={external_payment_id}"
        )
        return False
