"""
Фоновый воркер для периодической синхронизации транзакций.
"""

import asyncio
import logging

from apps.agents.services.payment_sync_service import PaymentSyncService

logger = logging.getLogger(__name__)


class PaymentSyncWorker:
    """
    Фоновый воркер для периодической синхронизации pending транзакций.
    Запасной механизм на случай если webhook не приходят.
    """
    
    def __init__(self, sync_interval: int = 3600):
        """
        Args:
            sync_interval: Интервал синхронизации в секундах (по умолчанию 1 час)
        """
        self.sync_interval = sync_interval
        self.sync_service = PaymentSyncService()
        self.is_running = False
        self.task = None
    
    async def start(self):
        """Запускает фоновую синхронизацию"""
        
        if self.is_running:
            logger.warning("Payment sync worker уже запущен")
            return
        
        self.is_running = True
        self.task = asyncio.create_task(self._sync_loop())
        logger.info(f"🔄 Payment sync worker запущен (интервал: {self.sync_interval}с)")
    
    async def stop(self):
        """Останавливает фоновую синхронизацию"""
        
        self.is_running = False
        
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info("Payment sync worker остановлен")
    
    async def _sync_loop(self):
        """Цикл периодической синхронизации"""
        
        # Первая синхронизация сразу после старта (через 30 секунд)
        await asyncio.sleep(30)
        
        while self.is_running:
            try:
                logger.info("🔄 Запуск периодической синхронизации транзакций")
                
                stats = await self.sync_service.sync_all_companies()
                
                if stats["total_updated"] > 0:
                    logger.info(
                        f"✅ Синхронизация завершена: "
                        f"найдено и обновлено {stats['total_updated']} транзакций"
                    )
                elif stats["total_pending"] > 0:
                    logger.info(
                        f"ℹ️ Синхронизация завершена: "
                        f"pending={stats['total_pending']}, но не найдено в провайдере"
                    )
                
                # Ждем до следующей синхронизации
                await asyncio.sleep(self.sync_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле синхронизации: {e}", exc_info=True)
                await asyncio.sleep(60)  # Ждем минуту при ошибке
