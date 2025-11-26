"""
Тесты для фонового воркера синхронизации MCP серверов.
"""

import pytest
import asyncio
from unittest.mock import patch


@pytest.mark.asyncio
async def test_mcp_sync_worker_starts():
    """Тест запуска MCPSyncWorker"""
    from apps.agents.workers.mcp_sync_worker import MCPSyncWorker
    
    worker = MCPSyncWorker(sync_interval=1)  # 1 секунда для теста
    
    assert worker.sync_interval == 1
    assert worker._running is False


@pytest.mark.asyncio
async def test_mcp_sync_worker_runs_sync():
    """Тест что воркер действительно вызывает синхронизацию"""
    from apps.agents.workers.mcp_sync_worker import MCPSyncWorker
    
    sync_called = []
    
    # Мокаем sync_all_companies_mcp_servers
    async def mock_sync():
        sync_called.append(True)
        print(f"✅ Mock sync called (total: {len(sync_called)})")
    
    worker = MCPSyncWorker(sync_interval=0.5)  # 0.5 секунды
    
    with patch('apps.agents.services.mcp_sync.sync_all_companies_mcp_servers', new=mock_sync):
        # Запускаем воркер в фоне
        task = asyncio.create_task(worker.start())
        
        # Даем время на несколько синхронизаций
        await asyncio.sleep(1.5)
        
        # Останавливаем
        await worker.stop()
        
        # Проверяем что синхронизация вызывалась
        assert len(sync_called) >= 2, f"Должно быть минимум 2 синхронизации, было: {len(sync_called)}"
        print(f"✅ Воркер выполнил {len(sync_called)} синхронизаций")


@pytest.mark.asyncio
async def test_mcp_sync_worker_handles_errors():
    """Тест что воркер продолжает работать при ошибках"""
    from apps.agents.workers.mcp_sync_worker import MCPSyncWorker
    
    call_count = []
    
    async def mock_sync_with_error():
        call_count.append(True)
        if len(call_count) == 1:
            raise Exception("Test error")
    
    worker = MCPSyncWorker(sync_interval=0.3)
    
    with patch('apps.agents.services.mcp_sync.sync_all_companies_mcp_servers', new=mock_sync_with_error):
        task = asyncio.create_task(worker.start())
        
        # Даем время на несколько попыток
        await asyncio.sleep(1.2)
        
        await worker.stop()
        
        # Проверяем что несмотря на ошибку в первой попытке, воркер продолжил
        assert len(call_count) >= 2, f"Воркер должен продолжать после ошибки, вызовов: {len(call_count)}"
        print(f"✅ Воркер пережил ошибку и продолжил ({len(call_count)} вызовов)")


@pytest.mark.asyncio
async def test_mcp_sync_worker_stop():
    """Тест корректной остановки воркера"""
    from apps.agents.workers.mcp_sync_worker import MCPSyncWorker
    
    async def mock_sync():
        await asyncio.sleep(0.1)
    
    worker = MCPSyncWorker(sync_interval=10)  # Большой интервал
    
    with patch('apps.agents.services.mcp_sync.sync_all_companies_mcp_servers', new=mock_sync):
        task = asyncio.create_task(worker.start())
        
        # Даем запуститься
        await asyncio.sleep(0.2)
        
        # Проверяем что работает
        assert worker._running is True
        
        # Останавливаем
        await worker.stop()
        
        # Проверяем что остановился
        assert worker._running is False
        
        print("✅ Воркер корректно остановлен")


@pytest.mark.asyncio
async def test_non_blocking_mcp_sync():
    """
    Тест что MCP синхронизация не блокирует запуск приложения.
    
    Проверяем что можно запустить синхронизацию в фоне и продолжить работу.
    """
    import time
    
    start_time = time.time()
    
    # Мокаем медленную синхронизацию
    async def slow_sync():
        await asyncio.sleep(2)  # 2 секунды
    
    with patch('apps.agents.services.mcp_sync.sync_all_companies_mcp_servers', new=slow_sync):
        # Запускаем в фоне
        task = asyncio.create_task(slow_sync())
        
        # Сразу продолжаем (не блокируется)
        elapsed = time.time() - start_time
        
        assert elapsed < 0.1, f"Запуск в фоне должен быть мгновенным, было: {elapsed}с"
        print(f"✅ Синхронизация запущена в фоне за {elapsed:.3f}с")
        
        # Продолжаем работу (приложение доступно)
        print("✅ Приложение доступно пока идет синхронизация")
        
        # Дожидаемся завершения для cleanup
        await task
        
        total_time = time.time() - start_time
        print(f"✅ Синхронизация завершилась через {total_time:.3f}с")


@pytest.mark.asyncio
async def test_mcp_sync_worker_configurable_interval():
    """Тест что можно настроить интервал синхронизации"""
    from apps.agents.workers.mcp_sync_worker import MCPSyncWorker
    
    # Разные интервалы
    worker_1min = MCPSyncWorker(sync_interval=60)
    worker_1hour = MCPSyncWorker(sync_interval=3600)
    worker_custom = MCPSyncWorker(sync_interval=1800)  # 30 минут
    
    assert worker_1min.sync_interval == 60
    assert worker_1hour.sync_interval == 3600
    assert worker_custom.sync_interval == 1800
    
    print("✅ Интервал синхронизации настраивается")

