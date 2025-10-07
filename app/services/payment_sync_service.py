"""
Сервис синхронизации транзакций с платежными провайдерами.
Запасной механизм на случай если webhook не приходят.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from ..core.storage import Storage
from ..core.clients.payment_providers.factory import PaymentProviderFactory
from ..models.payment_models import Transaction, PaymentStatus
from .payment_service import PaymentService

logger = logging.getLogger(__name__)


class PaymentSyncService:
    """Сервис для синхронизации статусов транзакций с провайдерами"""
    
    def __init__(self):
        self.storage = Storage()
        self.payment_service = PaymentService()
    
    async def sync_pending_transactions(self, company_id: str) -> Dict[str, Any]:
        """
        Синхронизирует pending транзакции компании с провайдерами.
        Проверяет через API провайдера не пропустили ли webhook.
        
        Returns:
            Статистика синхронизации
        """
        
        logger.info(f"Начало синхронизации pending транзакций для компании {company_id}")
        
        # Получаем все pending транзакции компании
        all_transactions = await self.payment_service.get_company_transactions(
            company_id=company_id,
            limit=100,
            offset=0
        )
        
        pending_transactions = [
            t for t in all_transactions 
            if t.status == PaymentStatus.PENDING
        ]
        
        if not pending_transactions:
            logger.info(f"Нет pending транзакций для компании {company_id}")
            return {
                "total_pending": 0,
                "checked": 0,
                "found": 0,
                "updated": 0
            }
        
        logger.info(f"Найдено {len(pending_transactions)} pending транзакций")
        
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
            
            # Проверяем что провайдер поддерживает синхронизацию
            if not hasattr(provider, 'sync_pending_transactions'):
                logger.warning(f"Провайдер {provider_type} не поддерживает синхронизацию")
                continue
            
            # Синхронизируем
            try:
                txn_dicts = [
                    {
                        "transaction_id": t.transaction_id,
                        "amount": t.amount,
                        "created_at": t.created_at.isoformat()
                    }
                    for t in transactions
                ]
                
                found_operations = await provider.sync_pending_transactions(txn_dicts)
                
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
                    transaction = await self.payment_service.get_transaction(transaction_id)
                    if not transaction:
                        logger.warning(f"Транзакция {transaction_id} не найдена при синхронизации")
                        continue
                    
                    # Обновляем статус
                    if op.get("status") == "success" and transaction.status == PaymentStatus.PENDING:
                        transaction.status = PaymentStatus.SUCCESS
                        transaction.external_payment_id = op.get("operation_id")
                        transaction.completed_at = datetime.now(timezone.utc)
                        
                        # Сохраняем
                        await self.payment_service._save_transaction(transaction)
                        
                        # Пополняем баланс
                        await self.payment_service._update_company_balance(
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
        
        # Получаем все компании
        company_keys = await self.storage.list_by_prefix("company:", force_global=True)
        
        total_stats = {
            "companies_checked": 0,
            "total_pending": 0,
            "total_found": 0,
            "total_updated": 0,
            "errors": 0
        }
        
        for company_key in company_keys:
            try:
                company_id = company_key.split(":")[1]
                
                stats = await self.sync_pending_transactions(company_id)
                
                total_stats["companies_checked"] += 1
                total_stats["total_pending"] += stats["total_pending"]
                total_stats["total_found"] += stats["found"]
                total_stats["total_updated"] += stats["updated"]
                
            except Exception as e:
                logger.error(f"Ошибка синхронизации компании {company_key}: {e}")
                total_stats["errors"] += 1
        
        logger.info(
            f"Глобальная синхронизация завершена: "
            f"компаний={total_stats['companies_checked']}, "
            f"обновлено={total_stats['total_updated']}"
        )
        
        return total_stats
