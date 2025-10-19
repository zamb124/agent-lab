"""
Фоновый воркер для периодической синхронизации MCP серверов.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MCPSyncWorker:
    """Периодическая синхронизация MCP серверов"""
    
    def __init__(self, sync_interval: int = 3600):
        """
        Args:
            sync_interval: Интервал синхронизации в секундах (по умолчанию 1 час)
        """
        self.sync_interval = sync_interval
        self._task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self):
        """Запуск периодической синхронизации"""
        self._running = True
        logger.info(f"🔌 MCP sync worker запущен (интервал: {self.sync_interval}с)")
        
        while self._running:
            try:
                # Выполняем синхронизацию
                from app.core.mcp_sync import sync_all_companies_mcp_servers
                
                logger.info("🔄 Запуск периодической синхронизации MCP серверов...")
                await sync_all_companies_mcp_servers()
                logger.info("✅ Периодическая синхронизация MCP завершена")
                
            except Exception as e:
                logger.error(f"❌ Ошибка при периодической синхронизации MCP: {e}", exc_info=True)
            
            # Ждем до следующей синхронизации
            await asyncio.sleep(self.sync_interval)
    
    async def stop(self):
        """Остановка воркера"""
        logger.info("🛑 Остановка MCP sync worker...")
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("✅ MCP sync worker остановлен")

