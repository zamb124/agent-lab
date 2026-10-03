"""
Сервис для обработки платежей и пополнения баланса компаний.
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from core.clients.payment.base_provider import (
    BasePaymentProvider,
    PaymentProviderConfig,
    PaymentRequest,
    WebhookVerificationResult,
)
from core.clients.payment.tinkoff_token import (
    TINKOFF_ORDER_ID_MAX_LEN,
    TINKOFF_TRANSACTION_SUFFIX_HEX_LEN,
)
from core.db.storage import Storage
from core.logging import get_logger
from core.models.identity_models import Company, User
from core.models.payment_models import (
    BalanceGrantResult,
    CreatePaymentResponse,
    PaymentNotification,
    PaymentProviderType,
    PaymentStatus,
    PaymentSyncOperation,
    TinkoffNotificationPayload,
    Transaction,
    transaction_storage_key,
    transaction_storage_key_by_id,
)
from core.short_links.service import require_platform_public_base_url
from core.types import JsonObject
from core.utils.domain import build_company_subdomain_absolute_url, get_protocol

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


def new_payment_transaction_id(company_id: str) -> str:
    clean_company_id = company_id.strip()
    if clean_company_id == "":
        raise ValueError("company_id is required")
    if ":" in clean_company_id:
        raise ValueError("company_id must not contain ':'")
    suffix_len = TINKOFF_TRANSACTION_SUFFIX_HEX_LEN
    max_suffix = TINKOFF_ORDER_ID_MAX_LEN - len(clean_company_id) - 1
    if max_suffix < 8:
        raise ValueError(
            f"company_id too long for Tinkoff OrderId limit {TINKOFF_ORDER_ID_MAX_LEN}: "
            + clean_company_id
        )
    if suffix_len > max_suffix:
        suffix_len = max_suffix
    transaction_id = f"{clean_company_id}:{uuid.uuid4().hex[:suffix_len]}"
    if len(transaction_id) > TINKOFF_ORDER_ID_MAX_LEN:
        raise ValueError(
            f"transaction_id length {len(transaction_id)} exceeds Tinkoff OrderId limit "
            + str(TINKOFF_ORDER_ID_MAX_LEN)
        )
    return transaction_id


def _payment_provider_type(provider_name: str) -> PaymentProviderType:
    if provider_name in ("tinkoff", "tinkoff_main"):
        return PaymentProviderType.TINKOFF
    if provider_name == "grant":
        return PaymentProviderType.GRANT
    raise ValueError(f"Unknown provider: {provider_name}")


def _customer_email(user: User) -> str | None:
    if not user.emails:
        return None
    email = user.emails[0].strip()
    if email == "":
        raise ValueError("user email must be a non-empty string")
    return email


def payment_browser_return_url(
    *,
    host: str,
    company_subdomain: str,
    payment_result: str,
    transaction_id: str,
) -> str:
    if host.strip() == "":
        raise ValueError("host is required for payment redirects")
    if company_subdomain.strip() == "":
        raise ValueError("company.subdomain is required for payment redirects")
    if payment_result not in ("success", "fail"):
        raise ValueError(f"unsupported payment_result: {payment_result}")
    if transaction_id.strip() == "":
        raise ValueError("transaction_id is required for payment redirects")
    return build_company_subdomain_absolute_url(
        host_header=host,
        url_scheme=get_protocol(host),
        path="/billing",
        query=f"payment={payment_result}&transaction_id={transaction_id}",
        company_subdomain=company_subdomain,
    )


class PaymentService:
    """Сервис для работы с платежами"""

    def __init__(self, *, storage: Storage) -> None:
        self._storage: Storage = storage

    async def create_payment(
        self,
        company: Company,
        user: User,
        amount: float,
        provider: BasePaymentProvider[PaymentProviderConfig[str]],
        *,
        host: str,
    ) -> CreatePaymentResponse:
        transaction_id = new_payment_transaction_id(company.company_id)

        logger.info(
            "payments.create_requested",
            company_id=company.company_id,
            user_id=user.user_id,
            amount=amount,
            provider=provider.provider_name,
        )

        if company.subdomain is None:
            raise ValueError("company.subdomain is required for payment redirects")
        success_url = payment_browser_return_url(
            host=host,
            company_subdomain=company.subdomain,
            payment_result="success",
            transaction_id=transaction_id,
        )
        fail_url = payment_browser_return_url(
            host=host,
            company_subdomain=company.subdomain,
            payment_result="fail",
            transaction_id=transaction_id,
        )
        public_base = require_platform_public_base_url()
        notification_url = f"{public_base}/api/v1/payments/webhook/{provider.registry_name}"

        payment_request = PaymentRequest(
            amount=amount,
            company_id=company.company_id,
            user_id=user.user_id,
            transaction_id=transaction_id,
            success_url=success_url,
            fail_url=fail_url,
            notification_url=notification_url,
            customer_email=_customer_email(user),
            language="ru",
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
        transaction_id = new_payment_transaction_id(company_id)
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
        company = await Company.get(company_id)
        if not company:
            raise ValueError(f"Company {company_id} not found after grant")
        logger.info(
            "payments.balance_grant_applied",
            company_id=company_id,
            amount=round(amount, 2),
            grantor_user_id=grantor_user_id,
            transaction_id=transaction_id,
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
        raw_data: TinkoffNotificationPayload,
    ) -> None:
        logger.info(
            "payments.webhook_processing",
            provider=provider_name,
            transaction_id=verification_result.transaction_id,
            amount=verification_result.amount,
            status=verification_result.status,
        )

        notification_id = f"notif_{uuid.uuid4().hex[:16]}"
        provider_type = _payment_provider_type(provider_name)
        notification = PaymentNotification(
            notification_id=notification_id,
            provider=provider_type,
            transaction_id=verification_result.transaction_id,
            external_payment_id=verification_result.external_payment_id,
            raw_data=raw_data,
            processed=False,
        )

        transaction_id = verification_result.transaction_id
        amount = verification_result.amount
        status = verification_result.status
        if transaction_id is None or transaction_id == "":
            raise ValueError("Payment webhook missing transaction_id")
        if amount is None:
            raise ValueError("Payment webhook missing amount")
        if status is None or status == "":
            raise ValueError("Payment webhook missing status")

        await self._save_notification(notification)

        if ":" not in transaction_id:
            logger.warning(
                "payments.webhook_unknown_order_id",
                transaction_id=transaction_id,
            )
            notification.processed = True
            await self._save_notification(notification)
            return

        transaction = await self.get_transaction(transaction_id)

        if transaction is None:
            logger.warning(
                "payments.webhook_unknown_order_id",
                transaction_id=transaction_id,
            )
            notification.processed = True
            await self._save_notification(notification)
            return

        if abs(transaction.amount - amount) > 0.001:
            raise ValueError(
                "Payment webhook amount mismatch: "
                + f"transaction={transaction.amount} webhook={amount}"
            )

        if status == PaymentStatus.PENDING.value:
            notification.processed = True
            await self._save_notification(notification)
            return

        if transaction.status != PaymentStatus.PENDING:
            logger.warning(
                "payments.transaction_already_processed",
                transaction_id=transaction.transaction_id,
                status=transaction.status,
            )
            notification.processed = True
            await self._save_notification(notification)
            return

        transaction.external_payment_id = verification_result.external_payment_id
        transaction.completed_at = datetime.now(timezone.utc)

        if status == PaymentStatus.FAILED.value:
            transaction.status = PaymentStatus.FAILED
            await self.close_unsuccessful_payment(transaction)
            notification.processed = True
            await self._save_notification(notification)
            return

        if status == PaymentStatus.REFUNDED.value:
            transaction.status = PaymentStatus.REFUNDED
            await self.close_unsuccessful_payment(transaction)
            notification.processed = True
            await self._save_notification(notification)
            return

        if status != PaymentStatus.SUCCESS.value:
            raise ValueError(f"Unexpected payment webhook status: {status}")

        transaction.status = PaymentStatus.SUCCESS
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
            key = transaction_storage_key_by_id(
                company_id=company_id,
                payment_provider=provider_type,
                transaction_id=transaction_id,
            )
            data = await self._storage.get(key)
            if data is not None:
                logger.debug("payments.transaction.found", key=key)
                return Transaction.model_validate_json(data)

        return None

    async def get_company_transactions(
        self, company_id: str, limit: int = 50, offset: int = 0, provider_name: str | None = None
    ) -> list[Transaction]:
        if provider_name:
            prefix = f"payment:{company_id}:{provider_name}:"
        else:
            prefix = f"payment:{company_id}:"

        transactions: list[Transaction] = []
        raw_transactions = await self._storage.get_all_by_prefix(
            prefix,
            limit=offset + limit,
        )
        for data in raw_transactions.values():
            transaction = Transaction.model_validate_json(data)
            transactions.append(transaction)

        transactions.sort(key=lambda t: t.created_at, reverse=True)

        return transactions[offset : offset + limit]

    async def list_pending_transactions(
        self,
        *,
        prefix: str,
        limit: int,
        newest_first: bool,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> list[Transaction]:
        if not prefix.startswith("payment:"):
            raise ValueError("prefix must start with 'payment:'")
        payloads = await self._storage.list_by_prefix_json_text_equals(
            prefix,
            field="status",
            equals=PaymentStatus.PENDING.value,
            limit=limit,
            newest_first=newest_first,
            created_after=created_after,
            created_before=created_before,
        )
        return [Transaction.model_validate_json(payload) for payload in payloads]

    async def expire_unpaid_pending(self, transaction: Transaction) -> bool:
        stored = await self.get_transaction(transaction.transaction_id)
        if stored is None:
            return False
        if stored.status != PaymentStatus.PENDING:
            return False
        stored.status = PaymentStatus.FAILED
        stored.completed_at = datetime.now(timezone.utc)
        await self.close_unsuccessful_payment(stored)
        logger.info(
            "payments.pending_expired",
            transaction_id=stored.transaction_id,
            company_id=stored.company_id,
        )
        return True

    async def close_unsuccessful_payment(self, transaction: Transaction) -> None:
        if transaction.status not in {PaymentStatus.FAILED, PaymentStatus.REFUNDED}:
            raise ValueError(
                "close_unsuccessful_payment requires failed or refunded, got "
                + transaction.status.value
            )
        await self._save_transaction(transaction)

    async def apply_sync_operation(
        self,
        transaction: Transaction,
        operation: PaymentSyncOperation,
    ) -> bool:
        if transaction.status != PaymentStatus.PENDING:
            logger.warning(
                "payments.transaction_already_processed",
                transaction_id=transaction.transaction_id,
                status=transaction.status,
            )
            return False
        operation_id = operation.operation_id
        if operation_id is None or operation_id.strip() == "":
            raise ValueError("payment sync operation_id is required")
        transaction.external_payment_id = operation_id
        transaction.completed_at = datetime.now(timezone.utc)
        if operation.status == PaymentStatus.SUCCESS:
            transaction.status = PaymentStatus.SUCCESS
            return await self.finalize_successful_payment(transaction)
        if operation.status in {PaymentStatus.FAILED, PaymentStatus.REFUNDED}:
            transaction.status = operation.status
            await self.close_unsuccessful_payment(transaction)
            return True
        raise ValueError(f"unexpected payment sync status: {operation.status.value}")

    async def _save_transaction(self, transaction: Transaction) -> None:
        key = transaction_storage_key(transaction)

        logger.debug("payments.transaction.save", key=key)

        success = await self._storage.set(key, transaction.model_dump_json())

        logger.debug("payments.transaction.saved", success=success)

        logger.debug("payments.transaction_saved", redis_key=key)

    async def _save_notification(self, notification: PaymentNotification) -> None:
        """Сохраняет уведомление"""
        _ = await self._storage.set(
            f"payment_notification:{notification.notification_id}",
            notification.model_dump_json(),
        )

    async def finalize_successful_payment(self, transaction: Transaction) -> bool:
        """
        Атомарно фиксирует успешную транзакцию и зачисляет средства.

        Запись транзакции, claim внешней операции и изменение баланса выполняются в
        одной DB-транзакции. Повторные webhook/sync вызовы возвращают False после
        проверки Transaction.balance_applied под row lock.
        """
        company = await Transaction.finalize_credit(self._storage, transaction)
        if company is None:
            logger.warning(
                "payments.balance_already_applied",
                transaction_id=transaction.transaction_id,
                company_id=transaction.company_id,
                amount=transaction.amount,
            )
            return False
        logger.info(
            "payments.balance_updated",
            company_id=transaction.company_id,
            balance_before=round(company.balance - transaction.amount, 2),
            balance_after=round(company.balance, 2),
            delta=round(transaction.amount, 2),
        )
        return True
