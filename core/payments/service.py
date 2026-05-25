"""
Сервис для обработки платежей и пополнения баланса компаний.
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from core.clients.payment.base_provider import (
    BasePaymentProvider,
    PaymentProviderConfig,
    PaymentRequest,
    WebhookVerificationResult,
)
from core.config import get_settings
from core.db.storage import Storage
from core.logging import get_logger
from core.models.identity_models import Company, User
from core.models.payment_models import (
    BalanceGrantResult,
    CreatePaymentResponse,
    ExternalPaymentClaim,
    PaymentNotification,
    PaymentProviderType,
    PaymentStatus,
    Transaction,
)
from core.types import JsonObject
from core.utils.domain import PRIMARY_DOMAIN

if TYPE_CHECKING:
    from core.db.repositories.company_repository import CompanyRepository

logger = get_logger(__name__)


def _payment_provider_type(provider_name: str) -> PaymentProviderType:
    if provider_name in ("yoomoney", "yoomoney_main"):
        return PaymentProviderType.YOOMONEY
    if provider_name in ("yukassa", "yukassa_main"):
        return PaymentProviderType.YUKASSA
    if provider_name == "grant":
        return PaymentProviderType.GRANT
    raise ValueError(f"Неизвестный провайдер: {provider_name}")


def _transaction_key(transaction: Transaction) -> str:
    return (
        f"payment:{transaction.company_id}:"
        + f"{transaction.payment_provider.value}:{transaction.transaction_id}"
    )


def _transaction_key_by_id(
    *,
    company_id: str,
    payment_provider: PaymentProviderType,
    transaction_id: str,
) -> str:
    return f"payment:{company_id}:{payment_provider.value}:{transaction_id}"


def _external_payment_key(
    *, payment_provider: PaymentProviderType, external_payment_id: str
) -> str:
    return f"payment_external:{payment_provider.value}:{external_payment_id}"


class PaymentService:
    """Сервис для работы с платежами"""

    def __init__(self, *, company_repository: "CompanyRepository", storage: Storage) -> None:
        self._company_repository: CompanyRepository = company_repository
        self._storage: Storage = storage

    async def create_payment(
        self,
        company: Company,
        user: User,
        amount: float,
        provider: BasePaymentProvider[PaymentProviderConfig[str]],
    ) -> CreatePaymentResponse:
        """
        Создает транзакцию и генерирует URL для оплаты.

        Args:
            company: Компания, которая пополняет баланс
            user: Пользователь, который инициировал пополнение
            amount: Сумма пополнения
            provider: Платежный провайдер

        Returns:
            Данные созданной платёжной транзакции.
        """

        transaction_id = f"{company.company_id}:txn_{uuid.uuid4().hex[:16]}"

        logger.info(
            "payments.create_requested",
            company_id=company.company_id,
            user_id=user.user_id,
            amount=amount,
            provider=provider.provider_name,
        )

        # Формируем абсолютные URL для редиректов
        settings = get_settings()

        # Определяем базовый URL
        if settings.server.env == "local":
            base_url = f"http://{company.subdomain}.localhost:{settings.server.port}"
        else:
            # Для production используем PRIMARY_DOMAIN для единообразия payment callbacks
            base_url = f"https://{company.subdomain}.{PRIMARY_DOMAIN}"

        success_url = f"{base_url}/billing?payment=success&transaction_id={transaction_id}"
        fail_url = f"{base_url}/billing?payment=fail&transaction_id={transaction_id}"

        payment_request = PaymentRequest(
            amount=amount,
            company_id=company.company_id,
            user_id=user.user_id,
            transaction_id=transaction_id,
            success_url=success_url,
            fail_url=fail_url,
            metadata={
                "company_name": company.name,
                "user_name": user.name,
            },
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
            metadata=payment_response.metadata,
        )

        await self._save_transaction(transaction)

        logger.info(
            "payments.transaction_created",
            transaction_id=transaction_id,
            payment_url=payment_response.payment_url,
        )

        return CreatePaymentResponse(
            transaction_id=transaction_id,
            payment_url=payment_response.payment_url,
            provider=provider.provider_name,
            status=PaymentStatus.PENDING.value,
            amount=amount,
        )

    async def apply_balance_grant(
        self,
        *,
        company_id: str,
        amount: float,
        grantor_user_id: str,
        note: str | None = None,
    ) -> BalanceGrantResult:
        """
        Начисление баланса без платёжного провайдера (грант из админки system).
        Транзакция сразу success; источник — payment_provider=grant.
        """
        if amount < 0.01:
            raise ValueError("amount must be at least 0.01")
        now = datetime.now(timezone.utc)
        transaction_id = f"{company_id}:txn_{uuid.uuid4().hex[:16]}"
        meta: JsonObject = {
            "granted_by_user_id": grantor_user_id,
        }
        if note is not None and note != "":
            meta["note"] = note
        transaction = Transaction(
            transaction_id=transaction_id,
            company_id=company_id,
            user_id=grantor_user_id,
            amount=amount,
            status=PaymentStatus.SUCCESS,
            payment_provider=PaymentProviderType.GRANT,
            external_payment_id=None,
            payment_url=None,
            created_at=now,
            completed_at=now,
            metadata=meta,
        )
        _ = await self.finalize_successful_payment(transaction)
        company = await self._company_repository.get(company_id)
        if not company:
            raise ValueError(f"Company {company_id} not found after grant")
        logger.info(
            "Грант баланса: company=%s amount=%.2f RUB by=%s txn=%s",
            company_id,
            amount,
            grantor_user_id,
            transaction_id,
        )
        return BalanceGrantResult(
            transaction_id=transaction_id,
            company_id=company_id,
            amount=amount,
            balance=company.balance,
        )

    async def process_webhook(
        self,
        verification_result: WebhookVerificationResult,
        provider_name: str,
        raw_data: JsonObject,
    ) -> None:
        """
        Обрабатывает webhook от платежного провайдера.

        Args:
            verification_result: Результат проверки webhook
            provider_name: Имя провайдера
            raw_data: Сырые данные webhook
        """

        logger.info(
            "payments.webhook_processing",
            provider=provider_name,
            transaction_id=verification_result.transaction_id,
            amount=verification_result.amount,
        )

        notification_id = f"notif_{uuid.uuid4().hex[:16]}"

        provider_type = _payment_provider_type(provider_name)

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
            logger.info("payments.test_notification_ok")
            notification.processed = True
            await self._save_notification(notification)
            return

        transaction_id = verification_result.transaction_id
        amount = verification_result.amount
        if transaction_id is None or transaction_id == "":
            raise ValueError("Payment webhook missing transaction_id")
        if amount is None:
            raise ValueError("Payment webhook missing amount")

        await self._save_notification(notification)

        transaction = await self.get_transaction(transaction_id)

        if not transaction:
            logger.error(
                "payments.transaction_not_found",
                transaction_id=transaction_id,
            )
            raise ValueError(f"Transaction {transaction_id} not found")

        if transaction.status != PaymentStatus.PENDING:
            logger.warning(
                "payments.transaction_already_processed",
                transaction_id=transaction.transaction_id,
                status=transaction.status,
            )
            notification.processed = True
            await self._save_notification(notification)
            return

        transaction.status = PaymentStatus.SUCCESS
        transaction.external_payment_id = verification_result.external_payment_id
        transaction.completed_at = datetime.now(timezone.utc)

        balance_updated = await self.finalize_successful_payment(transaction)

        notification.processed = True
        await self._save_notification(notification)

        if not balance_updated:
            return

        logger.info(
            "payments.payment_processed",
            transaction_id=transaction.transaction_id,
            company_id=transaction.company_id,
            amount=transaction.amount,
        )

    async def get_transaction(self, transaction_id: str) -> Transaction | None:
        """Получает транзакцию по ID"""
        if ":" not in transaction_id:
            raise ValueError("transaction_id must include company_id prefix")

        company_id = transaction_id.split(":", 1)[0]

        for provider_type in PaymentProviderType:
            key = _transaction_key_by_id(
                company_id=company_id,
                payment_provider=provider_type,
                transaction_id=transaction_id,
            )
            data = await self._storage.get(key, force_global=True)
            if data is not None:
                logger.debug(f"Транзакция найдена по ключу: {key}")
                return Transaction.model_validate_json(data)

        return None

    async def get_company_transactions(
        self,
        company_id: str,
        limit: int = 50,
        offset: int = 0,
        provider_name: str | None = None
    ) -> list[Transaction]:
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

        transactions: list[Transaction] = []
        raw_transactions = await self._storage.get_all_by_prefix(
            prefix,
            limit=offset + limit,
            force_global=True,
        )
        for data in raw_transactions.values():
            transaction = Transaction.model_validate_json(data)
            transactions.append(transaction)

        transactions.sort(key=lambda t: t.created_at, reverse=True)

        return transactions[offset : offset + limit]

    async def _save_transaction(self, transaction: Transaction) -> None:
        """
        Сохраняет транзакцию с составным ключом.
        Формат: payment:{company_id}:{provider}:{transaction_id}

        ВАЖНО: transaction_id уже содержит company_id в формате {company_id}:txn_{uuid},
        поэтому используем его полностью в ключе.
        """
        key = _transaction_key(transaction)

        logger.debug(f"Сохраняем транзакцию по ключу: {key}")

        success = await self._storage.set(
            key,
            transaction.model_dump_json(),
            force_global=True
        )

        logger.debug(f"Результат сохранения транзакции: {success}")

        logger.debug("payments.transaction_saved", redis_key=key)

    async def _save_notification(self, notification: PaymentNotification) -> None:
        """Сохраняет уведомление"""
        _ = await self._storage.set(
            f"payment_notification:{notification.notification_id}",
            notification.model_dump_json(),
            force_global=True
        )

    async def _get_transaction_in_session(
        self,
        transaction: Transaction,
        session: AsyncSession,
    ) -> Transaction | None:
        data = await self._storage.get(
            _transaction_key(transaction),
            db_session=session,
            force_global=True,
            for_update=True,
        )
        if data is None:
            return None
        return Transaction.model_validate_json(data)

    async def _save_transaction_in_session(
        self,
        transaction: Transaction,
        session: AsyncSession,
    ) -> None:
        _ = await self._storage.set(
            _transaction_key(transaction),
            transaction.model_dump_json(),
            db_session=session,
            force_global=True,
        )

    async def _apply_company_balance_in_session(
        self,
        *,
        company_id: str,
        amount: float,
        session: AsyncSession,
    ) -> Company:
        company_key = f"company:{company_id}"
        raw_company = await self._storage.get(
            company_key,
            db_session=session,
            force_global=True,
            for_update=True,
        )
        if raw_company is None:
            raise ValueError(f"Company {company_id} not found")
        company = Company.model_validate_json(raw_company)
        balance_before = company.balance
        company.balance += amount
        _ = await self._storage.set(
            company_key,
            company.model_dump_json(),
            db_session=session,
            force_global=True,
        )
        logger.info(
            "payments.balance_updated",
            company_id=company_id,
            balance_before=round(balance_before, 2),
            balance_after=round(company.balance, 2),
            delta=round(amount, 2),
        )
        return company

    async def _claim_external_payment_id(
        self,
        *,
        transaction: Transaction,
        session: AsyncSession,
    ) -> None:
        external_payment_id = transaction.external_payment_id
        if external_payment_id is None:
            return
        if external_payment_id == "":
            raise ValueError("external_payment_id must be non-empty")
        claimed = await self._storage.insert_once(
            _external_payment_key(
                payment_provider=transaction.payment_provider,
                external_payment_id=external_payment_id,
            ),
            ExternalPaymentClaim(transaction_id=transaction.transaction_id).model_dump_json(),
            db_session=session,
            force_global=True,
        )
        if not claimed:
            raise ValueError(
                "External payment operation is already linked to another transaction: "
                + external_payment_id
            )

    async def finalize_successful_payment(self, transaction: Transaction) -> bool:
        """
        Атомарно фиксирует успешную транзакцию и зачисляет средства.

        Запись транзакции, claim внешней операции и изменение баланса выполняются в
        одной DB-транзакции. Повторные webhook/sync вызовы возвращают False после
        проверки Transaction.balance_applied под row lock.
        """
        if transaction.balance_applied:
            logger.warning(
                "payments.balance_already_applied",
                transaction_id=transaction.transaction_id,
                company_id=transaction.company_id,
                amount=transaction.amount,
            )
            return False

        async with self._storage.get_session() as session:
            async with session.begin():
                stored = await self._get_transaction_in_session(transaction, session)
                if stored is not None and stored.balance_applied:
                    logger.warning(
                        "payments.balance_already_applied",
                        transaction_id=stored.transaction_id,
                        company_id=stored.company_id,
                        amount=stored.amount,
                    )
                    return False
                effective_transaction = stored if stored is not None else transaction
                effective_transaction.status = PaymentStatus.SUCCESS
                effective_transaction.external_payment_id = transaction.external_payment_id
                effective_transaction.completed_at = transaction.completed_at
                effective_transaction.balance_applied = True
                await self._claim_external_payment_id(
                    transaction=effective_transaction,
                    session=session,
                )
                await self._save_transaction_in_session(effective_transaction, session)
                _ = await self._apply_company_balance_in_session(
                    company_id=effective_transaction.company_id,
                    amount=effective_transaction.amount,
                    session=session,
                )
        return True
