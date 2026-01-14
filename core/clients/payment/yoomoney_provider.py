"""
Провайдер для приема платежей через YooMoney (ЮMoney).
Использует Quickpay форму для приема платежей.

АДАПТИРОВАНО: убраны try-except блоки и локальные импорты
"""

import hashlib
import logging
from urllib.parse import urlencode
from typing import Dict, Any, Optional, Literal
from pydantic import Field

from core.clients.payment.base_provider import (
    BasePaymentProvider,
    PaymentProviderConfig,
    PaymentRequest,
    PaymentResponse,
    WebhookVerificationResult
)
from core.http import get_httpx_client

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
    client_id: Optional[str] = Field(default=None, description="OAuth client_id приложения")
    client_secret: Optional[str] = Field(default=None, description="OAuth client_secret приложения")
    access_token: Optional[str] = Field(default=None, description="OAuth access_token для API")
    api_url: str = Field(
        default="https://yoomoney.ru/api",
        description="URL YooMoney API"
    )


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
        """
        
        logger.info(f"Проверка webhook YooMoney: {webhook_data.get('label')}")
        
        required_fields = [
            'notification_type', 'operation_id', 'amount',
            'currency', 'datetime', 'sender', 'codepro', 'sha1_hash', 'label'
        ]
        
        for field in required_fields:
            if field not in webhook_data:
                logger.error(f"Отсутствует обязательное поле: {field}")
                return WebhookVerificationResult(
                    is_valid=False,
                    error_message="Missing required fields"
                )
        
        signature_string = (
            f"{webhook_data['notification_type']}&"
            f"{webhook_data['operation_id']}&"
            f"{webhook_data['amount']}&"
            f"{webhook_data['currency']}&"
            f"{webhook_data['datetime']}&"
            f"{webhook_data['sender']}&"
            f"{webhook_data['codepro']}&"
            f"{self.config.notification_secret}&"
            f"{webhook_data['label']}"
        )
        
        expected_hash = hashlib.sha1(signature_string.encode()).hexdigest()
        received_hash = webhook_data['sha1_hash']
        
        is_valid = expected_hash == received_hash
        
        if is_valid:
            logger.info(f"Webhook валиден: транзакция={webhook_data['label']}, сумма={webhook_data['amount']}")
        else:
            logger.error(f"Невалидная подпись webhook: expected={expected_hash}, received={received_hash}")
        
        return WebhookVerificationResult(
            is_valid=is_valid,
            transaction_id=webhook_data['label'] if is_valid else None,
            amount=float(webhook_data['amount']) if is_valid else None,
            external_payment_id=webhook_data['operation_id'] if is_valid else None,
            status="success" if is_valid else "unknown",
            error_message=None if is_valid else "Invalid signature"
        )
    
    async def check_payment_status(self, external_payment_id: str) -> str:
        """
        Проверяет статус платежа через YooMoney API.
        Требует access_token.
        """
        if not self.config.access_token:
            logger.warning("access_token не настроен, невозможно проверить статус")
            return "unknown"
        
        async with get_httpx_client(timeout=30.0) as client:
            response = await client.post(
                f"{self.config.api_url}/operation-history",
                headers={
                    "Authorization": f"Bearer {self.config.access_token}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "operation_id": external_payment_id
                }
            )
            response.raise_for_status()
            data = response.json()
        
        status = data.get('status', 'unknown')
        logger.info(f"Статус платежа {external_payment_id}: {status}")
        return status

