"""
Сервис синхронизации транзакций с платежными провайдерами.
Запасной механизм на случай если webhook не приходят.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any

from core.clients.payment.factory import PaymentProviderFactory
from core.models.payment_models import PaymentStatus
from .service import PaymentService

logger = logging.getLogger(__name__)


class PaymentSyncService:
    """Сервис для синхронизации статусов транзакций с провайдерами"""
    
    def __init__(self, payment_service: PaymentService):
        self._payment_service = payment_service
    
    async def sync_pending_transactions(self, company_id: str) -> Dict[str, Any]:
        """
        Синхронизирует pending транзакции компании с провайдерами.
        Проверяет через API провайдера не пропустили ли webhook.
        
        Returns:
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
            return {
                "total_pending": 0,
                "checked": 0,
                "found": 0,
                "updated": 0
            }
        
        logger.info(f"Компания {company_id}: найдено {len(pending_transactions)} pending транзакций для синхронизации")
        
        stats = {
            "total_pending": len(pending_transactions),
            "checked": 0,
            "found": 0,
            "updated": 0,
            "by_provider": {}
        }
        
        # Группируем по провайдерам
        by_provider = {}
        for txn in pending_transactions:
            provider_type = txn.payment_provider.value
            if provider_type not in by_provider:
                by_provider[provider_type] = []
            by_provider[provider_type].append(txn)
        
        # Синхронизируем с каждым провайдером
        for provider_type, transactions in by_provider.items():
            logger.info(f"Синхронизация {len(transactions)} транзакций с провайдером {provider_type}")
            
            # Получаем провайдер (ищем первый подходящий)
            provider = None
            for provider_name, p in PaymentProviderFactory.get_available_providers().items():
                if provider_type in provider_name or p.provider_name == provider_type:
                    provider = p
                    break
            
            if not provider:
                logger.warning(f"Провайдер {provider_type} не найден")
                continue
            
            if not hasattr(provider, 'sync_pending_transactions'):
                logger.warning(f"Провайдер {provider_type} не поддерживает синхронизацию")
                continue
            
            try:
                txn_dicts = [
                    {
                        "transaction_id": t.transaction_id,
                        "amount": t.amount,
                        "created_at": t.created_at.isoformat()
                    }
                    for t in transactions
                ]
                
                found_operations = await provider.sync_pending_transactions(
                    txn_dicts, storage=self._payment_service._storage,
                )
                
                stats["checked"] += len(transactions)
                stats["found"] += len(found_operations)
                stats["by_provider"][provider_type] = {
                    "checked": len(transactions),
                    "found": len(found_operations)
                }
                
                # Обновляем найденные транзакции
                for op in found_operations:
                    transaction_id = op["transaction_id"]
                    
                    # Получаем транзакцию
                    transaction = await self._payment_service.get_transaction(transaction_id)
                    if not transaction:
                        logger.warning(f"Транзакция {transaction_id} не найдена при синхронизации")
                        continue
                    
                    # Обновляем статус
                    if op.get("status") == "success" and transaction.status == PaymentStatus.PENDING:
                        transaction.status = PaymentStatus.SUCCESS
                        transaction.external_payment_id = op.get("operation_id")
                        transaction.completed_at = datetime.now(timezone.utc)
                        
                        # Сохраняем
                        await self._payment_service._save_transaction(transaction)
                        
                        await self._payment_service._update_company_balance(
                            transaction.company_id,
                            transaction.amount
                        )
                        
                        stats["updated"] += 1
                        
                        logger.info(
                            f"✅ Транзакция {transaction_id} обновлена через синхронизацию: "
                            f"operation_id={op.get('operation_id')}, amount={op.get('amount')}"
                        )
                
            except Exception as e:
                logger.error(f"Ошибка синхронизации с провайдером {provider_type}: {e}", exc_info=True)
        
        logger.info(
            f"Синхронизация завершена: проверено={stats['checked']}, "
            f"найдено={stats['found']}, обновлено={stats['updated']}"
        )
        
        return stats
    
    async def sync_all_companies(self) -> Dict[str, Any]:
        """
        Синхронизирует pending транзакции всех компаний.
        Запускается периодически (например, раз в час).
        """
        
        logger.info("Начало глобальной синхронизации транзакций")
        
        storage = self._payment_service._storage
        subdomain_keys = await storage.list_by_prefix("subdomain:", force_global=True)
        
        company_ids = []
        for subdomain_key in subdomain_keys:
            raw = await storage.get(subdomain_key, force_global=True)
            if not raw:
                continue

            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                cid = parsed.get("company_id")
            elif isinstance(parsed, str):
                cid = parsed
            else:
                logger.warning("Неожиданный формат subdomain записи %s: %s", subdomain_key, type(parsed).__name__)
                continue

            if cid:
                company_ids.append(cid)
        
        logger.info(f"Найдено компаний для синхронизации: {len(company_ids)}")
        
        total_stats = {
            "companies_checked": 0,
            "total_pending": 0,
            "total_found": 0,
            "total_updated": 0,
            "errors": 0
        }
        
        for company_id in company_ids:
            try:
                
                # Пропускаем системные/служебные ключи
                if company_id in ["main", "default", "template"]:
                    continue
                
                stats = await self.sync_pending_transactions(company_id)
                
                total_stats["companies_checked"] += 1
                
                # Логируем только если есть pending транзакции
                if stats["total_pending"] > 0:
                    total_stats["total_pending"] += stats["total_pending"]
                    total_stats["total_found"] += stats["found"]
                    total_stats["total_updated"] += stats["updated"]
                
            except Exception as e:
                logger.debug(f"Ошибка синхронизации компании {company_id}: {e}")
                total_stats["errors"] += 1
        
        if total_stats["total_updated"] > 0 or total_stats["total_pending"] > 0:
            logger.info(
                f"Глобальная синхронизация завершена: "
                f"компаний={total_stats['companies_checked']}, "
                f"pending={total_stats['total_pending']}, "
                f"обновлено={total_stats['total_updated']}"
            )
        else:
            logger.debug(f"Синхронизация: проверено {total_stats['companies_checked']} компаний, pending транзакций нет")
        
        return total_stats

