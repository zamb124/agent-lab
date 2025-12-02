"""
Сервис для обработки платежей и пополнения баланса компаний.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from typing import TYPE_CHECKING

from core.clients.payment.base_provider import (
    BasePaymentProvider,
    PaymentRequest,
    WebhookVerificationResult
)
from core.models.payment_models import (
    Transaction,
    PaymentNotification,
    PaymentStatus,
    PaymentProviderType
)
from core.models.identity_models import Company, User
from core.config import get_settings
from core.utils.domain import PRIMARY_DOMAIN

if TYPE_CHECKING:
    from core.db.repositories.company_repository import CompanyRepository

logger = logging.getLogger(__name__)


class PaymentService:
    """Сервис для работы с платежами"""
    
    def __init__(self, company_repository: "CompanyRepository"):
        self.company_repository = company_repository
        self._storage = company_repository._storage
    
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
        
        transaction_id = f"{company.company_id}:txn_{uuid.uuid4().hex[:16]}"
        
        logger.info(
            f"Создание платежа: компания={company.company_id}, "
            f"пользователь={user.user_id}, сумма={amount}₽, "
            f"провайдер={provider.provider_name}"
        )
        
        # Формируем абсолютные URL для редиректов
        settings = get_settings()
        
        # Определяем базовый URL
        if settings.server.env == "local":
            base_url = f"http://{company.subdomain}.localhost:{settings.server.port}"
        else:
            # Для production используем PRIMARY_DOMAIN для единообразия payment callbacks
            base_url = f"https://{company.subdomain}.{PRIMARY_DOMAIN}"
        
        success_url = f"{base_url}/frontend/billing?payment=success&transaction_id={transaction_id}"
        fail_url = f"{base_url}/frontend/billing?payment=fail&transaction_id={transaction_id}"
        
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
        
        # Если это тестовое уведомление - просто логируем и выходим
        if verification_result.status == "test":
            logger.info("✅ Тестовое уведомление обработано успешно")
            await self._save_notification(notification)
            return
        
        if await self._is_notification_duplicate(verification_result.external_payment_id):
            logger.warning(
                f"⚠️ Дубликат уведомления: external_id={verification_result.external_payment_id}"
            )
            return
        
        await self._save_notification(notification)
        
        transaction = await self.get_transaction(verification_result.transaction_id)
        
        if not transaction:
            # Попытка извлечь company_id из label (формат: company_id:txn_xxx)
            label_parts = verification_result.transaction_id.split(":", 1)
            
            if len(label_parts) == 2:
                company_id_from_label = label_parts[0]
                logger.warning(
                    f"⚠️ Транзакция {verification_result.transaction_id} не найдена в БД, "
                    f"но можем определить компанию из label: {company_id_from_label}"
                )
                
                # Создаем транзакцию на лету (восстановление)
                
                
                # Определяем тип провайдера
                provider_type_map = {
                    "yoomoney_main": PaymentProviderType.YOOMONEY,
                    "yukassa_main": PaymentProviderType.YUKASSA
                }
                provider_type = provider_type_map.get(provider_name, PaymentProviderType.YOOMONEY)
                
                transaction = Transaction(
                    transaction_id=verification_result.transaction_id,
                    company_id=company_id_from_label,
                    user_id="system_recovery",  # Неизвестен - помечаем как восстановление
                    amount=verification_result.amount,
                    status=PaymentStatus.SUCCESS,
                    payment_provider=provider_type,
                    external_payment_id=verification_result.external_payment_id,
                    completed_at=datetime.now(timezone.utc),
                    metadata={"recovered": True, "reason": "webhook_without_transaction"}
                )
                
                await self._save_transaction(transaction)
                
                logger.info(
                    f"✅ Транзакция восстановлена из webhook: {transaction.transaction_id}"
                )
            else:
                logger.error(
                    f"❌ Транзакция {verification_result.transaction_id} не найдена и не может быть восстановлена"
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
        # transaction_id может быть в формате:
        # 1. {company_id}:txn_{uuid} - современный формат
        # 2. txn_{uuid} - старый формат для обратной совместимости
        
        if ":" in transaction_id:
            company_id = transaction_id.split(":")[0]
            
            for provider_type in PaymentProviderType:
                key = f"payment:{company_id}:{provider_type.value}:{transaction_id}"
                data = await self._storage.get(key, force_global=True)
                if data:
                    logger.debug(f"Транзакция найдена по ключу: {key}")
                    return Transaction.model_validate_json(data)
        
        # Старый формат или не найдена - делаем полный перебор
        prefix = "payment:"
        keys = await self._storage.list_by_prefix(prefix, force_global=True)
        
        for key in keys:
            if key.endswith(f":{transaction_id}"):
                data = await self._storage.get(key, force_global=True)
                if data:
                    logger.debug(f"Транзакция найдена по ключу: {key}")
                    return Transaction.model_validate_json(data)
        
        logger.debug(f"Транзакция {transaction_id} не найдена")
        return None
    
    async def get_company_transactions(
        self,
        company_id: str,
        limit: int = 50,
        offset: int = 0,
        provider_name: Optional[str] = None
    ) -> List[Transaction]:
        """
        Получает список транзакций компании.
        
        Args:
            company_id: ID компании
            limit: Максимальное количество результатов
            offset: Смещение для пагинации
            provider_name: Опционально - фильтр по провайдеру
        """
        
        if provider_name:
            prefix = f"payment:{company_id}:{provider_name}:"
        else:
            prefix = f"payment:{company_id}:"
        
        keys = await self._storage.list_by_prefix(prefix, force_global=True)
        
        transactions = []
        for key in keys:
            data = await self._storage.get(key, force_global=True)
            if data:
                transaction = Transaction.model_validate_json(data)
                transactions.append(transaction)
        
        transactions.sort(key=lambda t: t.created_at, reverse=True)
        
        return transactions[offset:offset + limit]
    
    async def _save_transaction(self, transaction: Transaction):
        """
        Сохраняет транзакцию с составным ключом.
        Формат: payment:{company_id}:{provider}:{transaction_id}
        
        ВАЖНО: transaction_id уже содержит company_id в формате {company_id}:txn_{uuid},
        поэтому используем его полностью в ключе.
        """
        # Получаем короткое имя провайдера (yoomoney вместо yoomoney_main)
        provider_type = transaction.payment_provider.value  # yoomoney, yukassa
        
        # Используем transaction_id полностью (уже содержит company_id)
        key = f"payment:{transaction.company_id}:{provider_type}:{transaction.transaction_id}"
        
        logger.debug(f"Сохраняем транзакцию по ключу: {key}")
        
        success = await self._storage.set(
            key,
            transaction.model_dump_json(),
            force_global=True
        )
        
        logger.debug(f"Результат сохранения транзакции: {success}")
        
        logger.debug(f"💾 Транзакция сохранена с ключом: {key}")
    
    async def _save_notification(self, notification: PaymentNotification):
        """Сохраняет уведомление"""
        await self._storage.set(
            f"payment_notification:{notification.notification_id}",
            notification.model_dump_json(),
            force_global=True
        )
    
    async def _is_notification_duplicate(self, external_payment_id: str) -> bool:
        """Проверяет не было ли уже обработано это уведомление"""
        
        if not external_payment_id:
            return False
        
        prefix = "payment_notification:"
        keys = await self._storage.list_by_prefix(prefix, force_global=True)
        
        for key in keys:
            data = await self._storage.get(key, force_global=True)
            if data:
                notification = PaymentNotification.model_validate_json(data)
                if notification.external_payment_id == external_payment_id and notification.processed:
                    return True
        
        return False
    
    async def _update_company_balance(self, company_id: str, amount: float):
        """Пополняет баланс компании"""
        
        company = await self.company_repository.get(company_id)
        
        if not company:
            logger.error(f"Компания {company_id} не найдена")
            raise ValueError(f"Company {company_id} not found")
        
        old_balance = company.balance
        company.balance += amount
        
        await self.company_repository.set(company)
        
        logger.info(
            f"💰 Баланс компании {company_id} обновлен: "
            f"{old_balance:.2f}₽ → {company.balance:.2f}₽ (+{amount:.2f}₽)"
        )

