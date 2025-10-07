"""
Провайдер для приема платежей через YooMoney (ЮMoney).
Использует Quickpay форму для приема платежей.
"""

import hashlib
import logging
import aiohttp
from urllib.parse import urlencode
from typing import Dict, Any, Optional, Literal, List
from pydantic import Field
from datetime import datetime, timedelta

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
    client_id: Optional[str] = Field(default=None, description="OAuth client_id приложения")
    client_secret: Optional[str] = Field(default=None, description="OAuth client_secret приложения")
    access_token: Optional[str] = Field(default=None, description="OAuth access_token для API (получается через OAuth flow)")
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
        
        Документация: https://yoomoney.ru/docs/wallet/using-api/notification-p2p-incoming
        """
        
        logger.info("Проверка YooMoney webhook")
        
        # Проверяем тестовое уведомление
        is_test = webhook_data.get("test_notification") == "true"
        
        if is_test:
            logger.info("🧪 Получено тестовое уведомление от YooMoney")
            # Для тестового уведомления label пустой - просто проверяем подпись
            notification_type = webhook_data.get("notification_type")
            operation_id = webhook_data.get("operation_id")
            amount = webhook_data.get("amount")
            currency = webhook_data.get("currency", "643")
            datetime_str = webhook_data.get("datetime")
            sender = webhook_data.get("sender", "")
            codepro = webhook_data.get("codepro", "false")
            label = webhook_data.get("label", "")
            received_hash = webhook_data.get("sha1_hash")
            
            # Проверяем подпись
            check_string = (
                f"{notification_type}&{operation_id}&{amount}&{currency}&"
                f"{datetime_str}&{sender}&{codepro}&{self.config.notification_secret}&{label}"
            )
            
            calculated_hash = hashlib.sha1(check_string.encode('utf-8')).hexdigest()
            
            if calculated_hash == received_hash:
                logger.info("✅ Тестовое уведомление - подпись валидна!")
                return WebhookVerificationResult(
                    is_valid=True,
                    transaction_id=None,  # Тестовое - нет транзакции
                    amount=float(amount),
                    external_payment_id=operation_id,
                    status="test"
                )
            else:
                logger.error(f"❌ Тестовое уведомление - неверная подпись!")
                return WebhookVerificationResult(
                    is_valid=False,
                    error_message="Invalid test notification signature"
                )
        
        # Реальное уведомление
        notification_type = webhook_data.get("notification_type")
        operation_id = webhook_data.get("operation_id")
        
        # Для разных типов уведомлений используем разные поля суммы
        if notification_type == "card-incoming":
            amount = webhook_data.get("amount")  # Для card-incoming используем amount
        else:
            amount = webhook_data.get("withdraw_amount") or webhook_data.get("amount")  # Для p2p-incoming
        
        currency = webhook_data.get("currency", "643")
        datetime_str = webhook_data.get("datetime")
        sender = webhook_data.get("sender", "")  # Для card-incoming может быть пустым
        codepro = webhook_data.get("codepro", "false")
        label = webhook_data.get("label")
        received_hash = webhook_data.get("sha1_hash")
        
        # Для card-incoming sender пустой - это нормально
        if not all([notification_type, operation_id, amount, datetime_str, label, received_hash]):
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
    
    async def get_operation_history(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        label: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Получает историю операций через YooMoney API.
        Требует access_token.
        
        Документация: https://yoomoney.ru/docs/wallet/user-account/operation-history
        """
        
        if not self.config.access_token:
            logger.error("Нет access_token для работы с API YooMoney")
            return []
        
        params = {
            "records": 100,
            "type": "deposition"  # Только входящие
        }
        
        if start_date:
            params["from"] = start_date.isoformat()
        
        if end_date:
            params["till"] = end_date.isoformat()
        
        if label:
            params["label"] = label
        
        headers = {
            "Authorization": f"Bearer {self.config.access_token}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.config.api_url}/operation-history",
                    data=params,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Получено операций из YooMoney API: {len(data.get('operations', []))}")
                        return data.get("operations", [])
                    else:
                        error_text = await response.text()
                        logger.error(f"Ошибка получения истории операций: {response.status}, {error_text}")
                        return []
        except Exception as e:
            logger.error(f"Ошибка запроса к YooMoney API: {e}")
            return []
    
    async def sync_pending_transactions(self, pending_transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Синхронизирует статусы pending транзакций с YooMoney API.
        Ищет в истории операций по label (transaction_id).
        
        Args:
            pending_transactions: Список транзакций со статусом PENDING
            
        Returns:
            Список найденных операций из YooMoney
        """
        
        if not self.config.access_token:
            logger.warning("Нет access_token для синхронизации транзакций")
            return []
        
        # Получаем историю за последние 7 дней
        start_date = datetime.now() - timedelta(days=7)
        operations = await self.get_operation_history(start_date=start_date)
        
        # Мапим label -> operation
        operations_by_label = {}
        for op in operations:
            if op.get("label"):
                operations_by_label[op["label"]] = op
        
        # Ищем наши pending транзакции
        found_operations = []
        for txn in pending_transactions:
            transaction_id = txn.get("transaction_id")
            if transaction_id in operations_by_label:
                yoomoney_op = operations_by_label[transaction_id]
                found_operations.append({
                    "transaction_id": transaction_id,
                    "operation_id": yoomoney_op.get("operation_id"),
                    "amount": float(yoomoney_op.get("amount", 0)),
                    "datetime": yoomoney_op.get("datetime"),
                    "status": yoomoney_op.get("status"),  # success, in_progress
                    "yoomoney_data": yoomoney_op
                })
                logger.info(
                    f"✅ Найдена операция для транзакции {transaction_id}: "
                    f"operation_id={yoomoney_op.get('operation_id')}, "
                    f"amount={yoomoney_op.get('amount')}"
                )
        
        return found_operations
