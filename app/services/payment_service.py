"""
Сервис для обработки платежей и пополнения баланса компаний.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from ..core.storage import Storage
from ..core.clients.payment_providers.factory import PaymentProviderFactory
from ..core.clients.payment_providers.base_provider import (
    BasePaymentProvider,
    PaymentRequest,
    WebhookVerificationResult
)
from ..models.payment_models import (
    Transaction,
    PaymentNotification,
    PaymentStatus,
    PaymentProviderType
)
from ..identity.models import Company, User

logger = logging.getLogger(__name__)


class PaymentService:
    """Сервис для работы с платежами"""
    
    def __init__(self):
        self.storage = Storage()
    
    async def create_payment(
        self,
        company: Company,
        user: User,
        amount: float,
        provider: BasePaymentProvider
    ) -> Dict[str, Any]:
        """
        Создает транзакцию и генерирует URL для оплаты.
        
        Args:
            company: Компания, которая пополняет баланс
            user: Пользователь, который инициировал пополнение
            amount: Сумма пополнения
            provider: Платежный провайдер
            
        Returns:
            Словарь с transaction_id и payment_url
        """
        
        transaction_id = f"txn_{uuid.uuid4().hex[:16]}"
        
        logger.info(
            f"Создание платежа: компания={company.company_id}, "
            f"пользователь={user.user_id}, сумма={amount}₽, "
            f"провайдер={provider.provider_name}"
        )
        
        success_url = f"/billing/payment/success?transaction_id={transaction_id}"
        fail_url = f"/billing/payment/fail?transaction_id={transaction_id}"
        
        payment_request = PaymentRequest(
            amount=amount,
            company_id=company.company_id,
            user_id=user.user_id,
            transaction_id=transaction_id,
            success_url=success_url,
            fail_url=fail_url,
            metadata={
                "company_name": company.name,
                "user_name": user.name
            }
        )
        
        payment_response = await provider.create_payment(payment_request)
        
        transaction = Transaction(
            transaction_id=transaction_id,
            company_id=company.company_id,
            user_id=user.user_id,
            amount=amount,
            status=PaymentStatus.PENDING,
            payment_provider=PaymentProviderType(provider.provider_name),
            external_payment_id=payment_response.external_payment_id,
            payment_url=payment_response.payment_url,
            metadata=payment_response.metadata
        )
        
        await self._save_transaction(transaction)
        
        logger.info(
            f"✅ Транзакция создана: ID={transaction_id}, "
            f"URL={payment_response.payment_url}"
        )
        
        return {
            "transaction_id": transaction_id,
            "payment_url": payment_response.payment_url,
            "amount": amount
        }
    
    async def process_webhook(
        self,
        verification_result: WebhookVerificationResult,
        provider_name: str,
        raw_data: Dict[str, Any]
    ):
        """
        Обрабатывает webhook от платежного провайдера.
        
        Args:
            verification_result: Результат проверки webhook
            provider_name: Имя провайдера
            raw_data: Сырые данные webhook
        """
        
        logger.info(
            f"Обработка webhook от {provider_name}: "
            f"транзакция={verification_result.transaction_id}, "
            f"сумма={verification_result.amount}₽"
        )
        
        notification_id = f"notif_{uuid.uuid4().hex[:16]}"
        
        # Мапим имя провайдера на тип
        provider_type_map = {
            "yoomoney_main": PaymentProviderType.YOOMONEY,
            "yukassa_main": PaymentProviderType.YUKASSA
        }
        
        provider_type = provider_type_map.get(provider_name)
        if not provider_type:
            # Пытаемся определить по типу из имени
            if "yoomoney" in provider_name:
                provider_type = PaymentProviderType.YOOMONEY
            elif "yukassa" in provider_name:
                provider_type = PaymentProviderType.YUKASSA
            else:
                raise ValueError(f"Неизвестный провайдер: {provider_name}")
        
        notification = PaymentNotification(
            notification_id=notification_id,
            provider=provider_type,
            transaction_id=verification_result.transaction_id,
            external_payment_id=verification_result.external_payment_id,
            raw_data=raw_data,
            processed=False
        )
        
        if await self._is_notification_duplicate(verification_result.external_payment_id):
            logger.warning(
                f"⚠️ Дубликат уведомления: external_id={verification_result.external_payment_id}"
            )
            return
        
        await self._save_notification(notification)
        
        transaction = await self.get_transaction(verification_result.transaction_id)
        
        if not transaction:
            logger.error(
                f"❌ Транзакция {verification_result.transaction_id} не найдена"
            )
            raise ValueError(f"Transaction {verification_result.transaction_id} not found")
        
        if transaction.status != PaymentStatus.PENDING:
            logger.warning(
                f"⚠️ Транзакция {transaction.transaction_id} уже обработана: "
                f"статус={transaction.status}"
            )
            return
        
        transaction.status = PaymentStatus.SUCCESS
        transaction.external_payment_id = verification_result.external_payment_id
        transaction.completed_at = datetime.now(timezone.utc)
        
        await self._save_transaction(transaction)
        
        await self._update_company_balance(
            transaction.company_id,
            transaction.amount
        )
        
        notification.processed = True
        await self._save_notification(notification)
        
        logger.info(
            f"✅ Платеж успешно обработан: транзакция={transaction.transaction_id}, "
            f"компания={transaction.company_id}, сумма={transaction.amount}₽"
        )
    
    async def get_transaction(self, transaction_id: str) -> Optional[Transaction]:
        """Получает транзакцию по ID"""
        data = await self.storage.get(
            f"transaction:{transaction_id}",
            force_global=True
        )
        
        if not data:
            return None
        
        return Transaction.model_validate_json(data)
    
    async def get_company_transactions(
        self,
        company_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Transaction]:
        """Получает список транзакций компании"""
        
        prefix = f"transaction:"
        keys = await self.storage.list_by_prefix(prefix, force_global=True)
        
        transactions = []
        for key in keys:
            data = await self.storage.get(key, force_global=True)
            if data:
                transaction = Transaction.model_validate_json(data)
                if transaction.company_id == company_id:
                    transactions.append(transaction)
        
        transactions.sort(key=lambda t: t.created_at, reverse=True)
        
        return transactions[offset:offset + limit]
    
    async def _save_transaction(self, transaction: Transaction):
        """Сохраняет транзакцию"""
        await self.storage.set(
            f"transaction:{transaction.transaction_id}",
            transaction.model_dump_json(),
            force_global=True
        )
    
    async def _save_notification(self, notification: PaymentNotification):
        """Сохраняет уведомление"""
        await self.storage.set(
            f"payment_notification:{notification.notification_id}",
            notification.model_dump_json(),
            force_global=True
        )
    
    async def _is_notification_duplicate(self, external_payment_id: str) -> bool:
        """Проверяет не было ли уже обработано это уведомление"""
        
        if not external_payment_id:
            return False
        
        prefix = "payment_notification:"
        keys = await self.storage.list_by_prefix(prefix, force_global=True)
        
        for key in keys:
            data = await self.storage.get(key, force_global=True)
            if data:
                notification = PaymentNotification.model_validate_json(data)
                if notification.external_payment_id == external_payment_id and notification.processed:
                    return True
        
        return False
    
    async def _update_company_balance(self, company_id: str, amount: float):
        """Пополняет баланс компании"""
        
        company_data = await self.storage.get(
            f"company:{company_id}",
            force_global=True
        )
        
        if not company_data:
            logger.error(f"❌ Компания {company_id} не найдена")
            raise ValueError(f"Company {company_id} not found")
        
        company = Company.model_validate_json(company_data)
        
        old_balance = company.balance
        company.balance += amount
        
        await self.storage.set(
            f"company:{company_id}",
            company.model_dump_json(),
            force_global=True
        )
        
        logger.info(
            f"💰 Баланс компании {company_id} обновлен: "
            f"{old_balance:.2f}₽ → {company.balance:.2f}₽ (+{amount:.2f}₽)"
        )
