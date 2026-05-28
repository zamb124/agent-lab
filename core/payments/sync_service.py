"""
Сервис синхронизации транзакций с платежными провайдерами.
"""

from datetime import datetime, timezone

from core.clients.payment.factory import PaymentProviderFactory
from core.db.storage import Storage
from core.logging import get_logger
from core.models.payment_models import (
    PaymentProviderSyncStats,
    PaymentProviderType,
    PaymentStatus,
    PaymentSyncAllCompaniesStats,
    PaymentSyncCandidate,
    PaymentSyncStats,
    Transaction,
)
from core.types import parse_json_value, require_json_object

from .service import PaymentService

logger = get_logger(__name__)


class PaymentSyncService:
    """Сервис для синхронизации статусов транзакций с провайдерами"""

    def __init__(self, *, payment_service: PaymentService, storage: Storage) -> None:
        self._payment_service: PaymentService = payment_service
        self._storage: Storage = storage

    async def sync_pending_transactions(self, company_id: str) -> PaymentSyncStats:
        """
        Синхронизирует pending транзакции компании с провайдерами.
        Проверяет через API провайдера не пропустили ли webhook.

        Возвращает:
            Статистика синхронизации
        """

        logger.debug(f"Проверка pending транзакций для компании {company_id}")

        all_transactions = await self._payment_service.get_company_transactions(
            company_id=company_id,
            limit=100,
            offset=0
        )

        pending_transactions = [
            t for t in all_transactions
            if t.status == PaymentStatus.PENDING
        ]

        if not pending_transactions:
            return PaymentSyncStats()

        logger.info(f"Компания {company_id}: найдено {len(pending_transactions)} pending транзакций для синхронизации")

        checked = 0
        found = 0
        updated = 0
        by_provider_stats: dict[PaymentProviderType, PaymentProviderSyncStats] = {}

        by_provider: dict[PaymentProviderType, list[Transaction]] = {}
        for txn in pending_transactions:
            provider_type = txn.payment_provider
            if provider_type not in by_provider:
                by_provider[provider_type] = []
            by_provider[provider_type].append(txn)

        for provider_type, transactions in by_provider.items():
            logger.info(f"Синхронизация {len(transactions)} транзакций с провайдером {provider_type.value}")

            provider = None
            for provider_name, p in PaymentProviderFactory.get_available_providers().items():
                if provider_name == provider_type.value or p.provider_name == provider_type.value:
                    provider = p
                    break

            if not provider:
                logger.warning(f"Провайдер {provider_type.value} не найден")
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
            if not found_operations:
                logger.debug("Провайдер %s не вернул pending-операций для синхронизации", provider_type)

            checked += len(transactions)
            found += len(found_operations)
            by_provider_stats[provider_type] = PaymentProviderSyncStats(
                checked=len(transactions),
                found=len(found_operations),
            )

            for op in found_operations:
                transaction_id = op.transaction_id

                transaction = await self._payment_service.get_transaction(transaction_id)
                if not transaction:
                    logger.warning(f"Транзакция {transaction_id} не найдена при синхронизации")
                    continue

                if op.status == PaymentStatus.SUCCESS and transaction.status == PaymentStatus.PENDING:
                    transaction.status = PaymentStatus.SUCCESS
                    transaction.external_payment_id = op.operation_id
                    transaction.completed_at = datetime.now(timezone.utc)

                    balance_updated = await self._payment_service.finalize_successful_payment(transaction)

                    if balance_updated:
                        updated += 1

                    logger.info(
                        "payments.transaction_synced",
                        transaction_id=transaction_id,
                        operation_id=op.operation_id,
                        amount=op.amount,
                    )

        logger.info(
            "Синхронизация завершена: проверено=%s, найдено=%s, обновлено=%s",
            checked,
            found,
            updated,
        )

        return PaymentSyncStats(
            total_pending=len(pending_transactions),
            checked=checked,
            found=found,
            updated=updated,
            by_provider=by_provider_stats,
        )

    async def sync_all_companies(self) -> PaymentSyncAllCompaniesStats:
        """
        Синхронизирует pending транзакции всех компаний.
        Запускается периодически (например, раз в час).
        """

        logger.info("Начало глобальной синхронизации транзакций")

        storage = self._storage
        subdomain_keys = await storage.list_by_prefix("subdomain:", force_global=True)

        company_ids: list[str] = []
        for subdomain_key in subdomain_keys:
            raw = await storage.get(subdomain_key, force_global=True)
            if not raw:
                continue

            parsed = parse_json_value(raw, f"subdomain record {subdomain_key}")
            if isinstance(parsed, dict):
                parsed_object = require_json_object(parsed, f"subdomain record {subdomain_key}")
                cid = parsed_object.get("company_id")
            elif isinstance(parsed, str):
                cid = parsed
            else:
                logger.warning("Неожиданный формат subdomain записи %s: %s", subdomain_key, type(parsed).__name__)
                continue

            if isinstance(cid, str) and cid != "":
                company_ids.append(cid)

        logger.info(f"Найдено компаний для синхронизации: {len(company_ids)}")

        total_stats = PaymentSyncAllCompaniesStats()

        for company_id in company_ids:
            if company_id in ["main", "default", "template"]:
                continue

            stats = await self.sync_pending_transactions(company_id)

            total_stats.companies_checked += 1

            if stats.total_pending > 0:
                total_stats.total_pending += stats.total_pending
                total_stats.total_found += stats.found
                total_stats.total_updated += stats.updated

        if total_stats.total_updated > 0 or total_stats.total_pending > 0:
            logger.info(
                "Глобальная синхронизация завершена: компаний=%s, pending=%s, обновлено=%s",
                total_stats.companies_checked,
                total_stats.total_pending,
                total_stats.total_updated,
            )
        else:
            logger.debug(f"Синхронизация: проверено {total_stats.companies_checked} компаний, pending транзакций нет")

        return total_stats
