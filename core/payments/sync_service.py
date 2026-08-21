"""
Сервис синхронизации транзакций с платежными провайдерами.
"""

from datetime import datetime, timedelta, timezone

from core.clients.payment.factory import PaymentProvider, PaymentProviderFactory
from core.config import get_settings
from core.db.storage import Storage
from core.logging import get_logger
from core.models.payment_models import (
    PaymentProviderSyncStats,
    PaymentProviderType,
    PaymentSyncAllCompaniesStats,
    PaymentSyncCandidate,
    PaymentSyncStats,
    Transaction,
)

from .service import PaymentService

logger = get_logger(__name__)


def _provider_for(provider_type: PaymentProviderType) -> PaymentProvider | None:
    for provider_name, provider in PaymentProviderFactory.get_available_providers().items():
        if provider_name == provider_type.value or provider.provider_name == provider_type.value:
            return provider
    return None


def _combine_stats(first: PaymentSyncStats, second: PaymentSyncStats) -> PaymentSyncStats:
    by_provider: dict[PaymentProviderType, PaymentProviderSyncStats] = dict(first.by_provider)
    for provider_type, stats in second.by_provider.items():
        existing = by_provider.get(provider_type)
        if existing is None:
            by_provider[provider_type] = stats
            continue
        by_provider[provider_type] = PaymentProviderSyncStats(
            checked=existing.checked + stats.checked,
            found=existing.found + stats.found,
        )
    return PaymentSyncStats(
        total_pending=first.total_pending + second.total_pending,
        checked=first.checked + second.checked,
        found=first.found + second.found,
        updated=first.updated + second.updated,
        by_provider=by_provider,
    )


class PaymentSyncService:
    """Сверка pending с банком: запасной канал к webhook."""

    def __init__(self, *, payment_service: PaymentService, storage: Storage) -> None:
        self._payment_service: PaymentService = payment_service
        self._storage: Storage = storage

    async def sync_pending_transactions(self, company_id: str) -> PaymentSyncStats:
        clean_company_id = company_id.strip()
        if clean_company_id == "":
            raise ValueError("company_id is required")
        stats, _company_ids = await self._sync_prefix(f"payment:{clean_company_id}:")
        return stats

    async def sync_all_companies(self) -> PaymentSyncAllCompaniesStats:
        logger.info("Начало глобальной синхронизации транзакций")
        stats, company_ids = await self._sync_prefix("payment:")
        total_stats = PaymentSyncAllCompaniesStats(
            companies_checked=len(company_ids),
            total_pending=stats.total_pending,
            total_found=stats.found,
            total_updated=stats.updated,
        )
        if total_stats.total_updated > 0 or total_stats.total_pending > 0:
            logger.info(
                "Глобальная синхронизация завершена: компаний=%s, pending=%s, обновлено=%s",
                total_stats.companies_checked,
                total_stats.total_pending,
                total_stats.total_updated,
            )
        else:
            logger.debug("Синхронизация: живых pending нет")
        return total_stats

    async def _sync_prefix(self, prefix: str) -> tuple[PaymentSyncStats, set[str]]:
        cfg = get_settings().payment_providers
        window_start = datetime.now(timezone.utc) - timedelta(hours=cfg.sync_pending_max_age_hours)
        check_limit = cfg.sync_check_order_limit

        expired = await self._payment_service.list_pending_transactions(
            prefix=prefix,
            limit=check_limit,
            newest_first=False,
            created_before=window_start,
        )
        remaining = check_limit - len(expired)
        in_window: list[Transaction] = []
        if remaining > 0:
            in_window = await self._payment_service.list_pending_transactions(
                prefix=prefix,
                limit=remaining,
                newest_first=True,
                created_after=window_start,
            )

        expired_stats = await self._sync_transaction_batch(
            expired,
            expire_if_unresolved=True,
        )
        in_window_stats = await self._sync_transaction_batch(
            in_window,
            expire_if_unresolved=False,
        )
        stats = _combine_stats(expired_stats, in_window_stats)
        company_ids = {txn.company_id for txn in expired}
        company_ids.update(txn.company_id for txn in in_window)
        return stats, company_ids

    async def _sync_transaction_batch(
        self,
        pending_transactions: list[Transaction],
        *,
        expire_if_unresolved: bool,
    ) -> PaymentSyncStats:
        if not pending_transactions:
            return PaymentSyncStats()

        checked = 0
        found = 0
        updated = 0
        by_provider_stats: dict[PaymentProviderType, PaymentProviderSyncStats] = {}

        by_provider: dict[PaymentProviderType, list[Transaction]] = {}
        for txn in pending_transactions:
            provider_type = txn.payment_provider
            bucket = by_provider.get(provider_type)
            if bucket is None:
                bucket = []
                by_provider[provider_type] = bucket
            bucket.append(txn)

        for provider_type, transactions in by_provider.items():
            provider = _provider_for(provider_type)
            if provider is None:
                logger.warning("Провайдер %s не найден", provider_type.value)
                if expire_if_unresolved:
                    for txn in transactions:
                        if await self._payment_service.expire_unpaid_pending(txn):
                            updated += 1
                continue

            sync_candidates = [
                PaymentSyncCandidate(
                    transaction_id=t.transaction_id,
                    amount=t.amount,
                    created_at=t.created_at,
                )
                for t in transactions
            ]
            found_operations = await provider.sync_pending_transactions(
                sync_candidates,
                storage=self._storage,
            )
            checked += len(transactions)
            found += len(found_operations)
            by_provider_stats[provider_type] = PaymentProviderSyncStats(
                checked=len(transactions),
                found=len(found_operations),
            )
            resolved_ids: set[str] = set()
            for op in found_operations:
                transaction_id = op.transaction_id
                transaction = await self._payment_service.get_transaction(transaction_id)
                if transaction is None:
                    logger.warning("Транзакция %s не найдена при синхронизации", transaction_id)
                    continue
                applied = await self._payment_service.apply_sync_operation(transaction, op)
                resolved_ids.add(transaction_id)
                if applied:
                    updated += 1
                    logger.info(
                        "payments.transaction_synced",
                        transaction_id=transaction_id,
                        operation_id=op.operation_id,
                        amount=op.amount,
                        status=op.status.value,
                    )
            if expire_if_unresolved:
                for txn in transactions:
                    if txn.transaction_id in resolved_ids:
                        continue
                    if await self._payment_service.expire_unpaid_pending(txn):
                        updated += 1

        logger.info(
            "Синхронизация пакета: pending=%s, проверено=%s, найдено=%s, обновлено=%s, expire=%s",
            len(pending_transactions),
            checked,
            found,
            updated,
            expire_if_unresolved,
        )
        return PaymentSyncStats(
            total_pending=len(pending_transactions),
            checked=checked,
            found=found,
            updated=updated,
            by_provider=by_provider_stats,
        )
