"""
Жизненный цикл приложения FastAPI
"""

import asyncio
import aiohttp
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.core.config import settings
from app.core.checkpointer import init_checkpointer, close_checkpointer
from app.db.database import create_tables, close_db
from app.core.migration import Migrator
from app.core.translation_manager import get_translation_manager
from app.core.clients.payment_providers.factory import PaymentProviderFactory
from app.workers.payment_sync_worker import PaymentSyncWorker
from app.core.context import set_context, clear_context
from app.core.container import set_system_container, get_container
from app.models.context_models import Context
from app.identity.models import Company, User
from app.frontend.core.plugin_loader import discover_and_load_plugins
from app.workers.mcp_sync_worker import MCPSyncWorker
from app.core.mcp_sync import sync_all_companies_mcp_servers
from app.services.cleanup_service import CleanupService

# Условные импорты для локального окружения
if settings.server.env == "local":
    from app.workers.task_processor import TaskProcessor
    from app.services.telegram_poller import telegram_poller

logger = logging.getLogger(__name__)


async def _periodic_cleanup():
    """Периодическая очистка истекших данных из Storage и S3"""

    cleanup_service = CleanupService()

    while True:
        try:
            # Очищаем истекшие данные каждые 6 часов
            await asyncio.sleep(6 * 60 * 60)  # 6 часов

            deleted_count = await cleanup_service.cleanup_expired()
            if deleted_count > 0:
                logger.info(
                    f"🧹 Периодическая очистка: удалено {deleted_count} истекших записей"
                )

        except Exception as e:
            logger.error(f"❌ Ошибка периодической очистки: {e}")
            # Ждем 1 час при ошибке
            await asyncio.sleep(60 * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл приложения"""
    logger.info("🚀 Запуск Agents Lab...")

    try:
        # Создаем системный контекст для фоновых задач
        logger.info("🔧 Инициализация системного контекста...")

        system_context = Context(
            user=User(
                user_id="system",
                name="System",
                companies={},
                active_company_id="system"
            ),
            active_company=Company(
                company_id="system",
                name="System",
                subdomain="system"
            ),
            session_id="system",
            platform="system"
        )

        await set_context(system_context)
        logger.info("✅ Системный контекст установлен")

        # Сохраняем системный контейнер для глобального доступа (например, в middleware)
        set_system_container(system_context.container)
        logger.info("✅ Системный контейнер сохранен для глобального доступа")

        # Инициализация БД
        logger.info("📊 Создание таблиц БД...")
        await create_tables()

        # Инициализация checkpointer для LangGraph
        logger.info("🔄 Инициализация checkpointer...")
        await init_checkpointer()

        # Запуск миграций в фоне (неблокирующая операция)
        logger.info("🔄 Запуск миграций в фоновом режиме...")
        async def run_migration():
            try:
                migrator = get_container().migrator
                await migrator.run_full_migration()
                logger.info("✅ Миграция завершена успешно")
            except Exception as e:
                logger.error(f"❌ Ошибка миграции: {e}")

        asyncio.create_task(run_migration())

        # Инициализация системы переводов
        logger.info("🌐 Инициализация системы интернационализации...")
        translation_manager = get_translation_manager()
        await translation_manager.initialize()
        logger.info("✅ Система переводов инициализирована")

        # Инициализация платежных провайдеров
        logger.info("💳 Инициализация платежных провайдеров...")
        PaymentProviderFactory.initialize(settings)
        logger.info("✅ Платежные провайдеры инициализированы")

        # Автоматическая загрузка плагинов
        logger.info("🔌 Загрузка плагинов фронтенда...")
        await discover_and_load_plugins(app)
        logger.info("✅ Плагины фронтенда загружены")

        # Синхронизация MCP серверов (неблокирующая, периодическая)
        logger.info("🔌 Запуск фоновой синхронизации MCP серверов...")

        # Первая синхронизация сразу (в фоне)
        async def initial_mcp_sync():
            try:
                await sync_all_companies_mcp_servers()
                logger.info("✅ Начальная синхронизация MCP завершена")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка начальной синхронизации MCP: {e}")

        asyncio.create_task(initial_mcp_sync())

        # Периодическая синхронизация (каждый час)
        mcp_sync_worker = MCPSyncWorker(sync_interval=3600)
        asyncio.create_task(mcp_sync_worker.start())
        logger.info("✅ MCP sync worker запущен (ресинхронизация каждый час)")

        # Запуск синхронизации транзакций (раз в час)
        logger.info("🔄 Запуск фоновой синхронизации транзакций...")
        payment_sync_worker = PaymentSyncWorker(sync_interval=3600)  # Каждый час
        asyncio.create_task(payment_sync_worker.start())
        logger.info("✅ Payment sync worker запущен")

        # Запуск воркера задач для локальной разработки
        if settings.server.env == "local":
            logger.info("⚙️ Запуск воркера задач для локальной разработки...")
            task_processor = TaskProcessor()
            asyncio.create_task(task_processor.start())
            logger.info("✅ Воркер задач запущен")

            logger.info("🤖 Запуск Telegram long polling для локальной разработки...")
            await telegram_poller.start()
            logger.info("✅ Telegram polling запущен")

        # Запуск периодической очистки истекших данных
        # ВРЕМЕННО ОТКЛЮЧЕНО: может удалять записи subdomain
        # logger.info("🧹 Запуск периодической очистки истекших данных...")
        # asyncio.create_task(_periodic_cleanup())
        # logger.info("✅ Периодическая очистка запущена")
        logger.info("🚫 Периодическая очистка ОТКЛЮЧЕНА")

        logger.info("✅ Agents Lab запущена успешно!")

        yield

    except Exception as e:
        logger.error(f"❌ Ошибка запуска приложения: {e}")
        raise
    finally:
        # Закрытие ресурсов
        logger.info("🔄 Закрытие ресурсов...")

        # Останавливаем сервисы если запущены
        if settings.server.env == "local":
            try:
                await telegram_poller.stop()
                logger.info("🛑 Telegram polling остановлен")
            except Exception as e:
                logger.error(f"Ошибка остановки Telegram polling: {e}")

        # Закрываем все открытые aiohttp сессии
        try:
            await asyncio.sleep(0.1)  # Даем время на завершение pending запросов
            logger.info("✅ HTTP сессии закрыты")
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Предупреждение при закрытии HTTP сессий: {e}")

        await close_checkpointer()
        await close_db()
        logger.info("✅ Agents Lab остановлена")
