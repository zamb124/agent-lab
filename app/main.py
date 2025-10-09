"""
Главная точка входа FastAPI приложения.
"""

import logging
import asyncio
import json
import re
import uvicorn
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.config import settings
from app.core.checkpointer import init_checkpointer, close_checkpointer
from app.db.database import create_tables, close_db
from app.core.migrator import Migrator
from app.api.amocrm import router as amocrm_router
from app.api.v1 import webhooks, admin, telegram, whatsapp, tokens, auth, flows, fashn, files, leads, history, payments, admin_payments, variables, knowledge_base
from app.frontend.api import models as frontend_models
from app.frontend.api import flows as frontend_flows
from app.frontend.api import agents as frontend_agents
from app.frontend.api import tools as frontend_tools
from app.frontend.api import variables as frontend_variables
from app.frontend.api import i18n as frontend_i18n
from app.frontend.pages import auth as auth_pages
from app.frontend.pages import dashboard as dashboard_pages
from app.frontend.pages import public as public_pages
from app.frontend.modules.chat import router as chat_module
from app.frontend.modules.chats.router import router as chats_module
from app.frontend.modules.builder import router as builder_module
from app.frontend.modules.billing.router import router as billing_module
from app.frontend.modules.admin.router import router as admin_module
from app.frontend.modules.history.router import router as history_module
from app.frontend.modules.bots.router import router as bots_module
from app.frontend.modules.variables.router import router as variables_module
from app.frontend.websockets import notifications as websocket_notifications
from app.frontend.websockets import chat as websocket_chat
from app.middleware.auth import AuthMiddleware
from app.services.cleanup_service import CleanupService
from app.core.translation_manager import get_translation_manager
from app.core.clients.payment_providers.factory import PaymentProviderFactory
from app.workers.payment_sync_worker import PaymentSyncWorker

# Условные импорты для локального окружения
if settings.server.env == "local":
    from app.workers.task_processor import TaskProcessor
    from app.services.telegram_poller import telegram_poller

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


# Custom formatter для красивого JSON в логах
class PrettyJSONFormatter(logging.Formatter):
    def format(self, record):
        msg = super().format(record)
        # Ищем JSON в сообщении и форматируем его
        if "json_data" in msg or "Request options" in msg or "Response" in msg:
            try:
                # Пытаемся найти и отформатировать JSON
                json_match = re.search(r"\{.*\}", msg, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    try:
                        json_obj = eval(json_str)  # Осторожно! Только для логов
                        pretty_json = json.dumps(json_obj, indent=2, ensure_ascii=False)
                        msg = msg.replace(json_str, f"\n{pretty_json}")
                    except Exception:
                        pass
            except Exception:
                pass
        return msg


# Применяем красивый форматтер к OpenAI и HTTP логам
for logger_name in ["openai._base_client", "openai", "httpx", "httpcore"]:
    logger_obj = logging.getLogger(logger_name)
    if logger_obj.handlers:
        for handler in logger_obj.handlers:
            handler.setFormatter(PrettyJSONFormatter())

# Включаем только OpenAI логи
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai._base_client").setLevel(logging.DEBUG)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("app.core.migrator").setLevel(logging.WARNING)
logging.getLogger("app.core.agent_factory").setLevel(logging.WARNING)
logging.getLogger("app.core.storage").setLevel(logging.WARNING)

# Оставляем только ключевые логи
logging.getLogger("app.agents.base").setLevel(
    logging.WARNING
)  # Убираем избыточные логи загрузки tools
logging.getLogger("app.workers.task_processor").setLevel(
    logging.INFO
)  # Основные логи воркера
logging.getLogger("app.tools.standard").setLevel(
    logging.WARNING
)  # Убираем технические логи ask_user
logging.getLogger("app.core.llm_factory").setLevel(
    logging.WARNING
)  # Отключаем wrapper логи

# Убираем детальные DEBUG логи uvicorn и websocket
logging.getLogger("uvicorn.protocols.websockets").setLevel(logging.WARNING)
logging.getLogger("uvicorn.protocols.http").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)
logging.getLogger("websockets.protocol").setLevel(logging.WARNING)
logging.getLogger("websockets.server").setLevel(logging.WARNING)
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
        # Инициализация БД
        logger.info("📊 Создание таблиц БД...")
        await create_tables()

        # Инициализация checkpointer для LangGraph
        logger.info("🔄 Инициализация checkpointer...")
        await init_checkpointer()

        # Запуск миграций
        logger.info("🔄 Запуск миграций...")
        migrator = Migrator()
        await migrator.run_full_migration()

        # Инициализация системы переводов
        logger.info("🌐 Инициализация системы интернационализации...")
        translation_manager = get_translation_manager()
        await translation_manager.initialize()
        logger.info("✅ Система переводов инициализирована")

        # Инициализация платежных провайдеров
        logger.info("💳 Инициализация платежных провайдеров...")
        PaymentProviderFactory.initialize(settings)
        logger.info("✅ Платежные провайдеры инициализированы")

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

        await close_checkpointer()
        await close_db()
        logger.info("✅ Agents Lab остановлена")


# Создание FastAPI приложения
app = FastAPI(
    title="Agents Lab",
    description="Платформа для создания и управления ИИ агентами с LangGraph",
    version="0.1.0",
    debug=settings.server.debug,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Proxy headers middleware (для правильной работы за nginx)
app.add_middleware(
    ProxyHeadersMiddleware,
    trusted_hosts=["*"] if settings.server.debug else [settings.server.domain, f"*.{settings.server.domain}"]
)

# Auth middleware (заглушка)
app.add_middleware(AuthMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.server.debug else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# UTF-8 middleware для правильной кодировки JSON ответов
@app.middleware("http")
async def utf8_response_middleware(request: Request, call_next):
    response = await call_next(request)
    if "application/json" in response.headers.get("content-type", ""):
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response

# Подключение роутеров

# API v1
app.include_router(webhooks.router, prefix="/api/v1", tags=["webhooks"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(telegram.router, prefix="/api/v1", tags=["telegram"])
app.include_router(whatsapp.router, prefix="/api/v1", tags=["whatsapp"])
app.include_router(tokens.router, prefix="/api/v1", tags=["tokens"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(flows.router, prefix="/api/v1/flows", tags=["flows"])
app.include_router(fashn.router, prefix="/api/v1/fashn", tags=["fashn"])
app.include_router(files.router, prefix="/api/v1/files", tags=["files"])
app.include_router(leads.router, prefix="/api/v1", tags=["leads"])
app.include_router(history.router, tags=["history"])
app.include_router(payments.router, prefix="/api/v1", tags=["payments"])
app.include_router(admin_payments.router, prefix="/api/v1", tags=["admin-payments"])
app.include_router(variables.router, prefix="/api/v1", tags=["variables"])
app.include_router(knowledge_base.router, prefix="/api/v1", tags=["knowledge-base"])

# Frontend API (JSON CRUD)
app.include_router(frontend_models.router, tags=["frontend-models"])  # Убираем дублирующий prefix
app.include_router(frontend_flows.router, prefix="/frontend/api", tags=["frontend-flows"])
app.include_router(frontend_agents.router, prefix="/frontend/api", tags=["frontend-agents"])
app.include_router(frontend_tools.router, prefix="/frontend/api", tags=["frontend-tools"])
app.include_router(frontend_variables.router, prefix="/frontend/api", tags=["frontend-variables"])
app.include_router(frontend_i18n.router, prefix="/frontend/api/i18n", tags=["frontend-i18n"])

# Frontend Pages (HTML)
app.include_router(public_pages.router, tags=["public-pages"])
app.include_router(auth_pages.router, tags=["auth-pages"])
app.include_router(dashboard_pages.router, tags=["dashboard-pages"])

# Frontend Modules
app.include_router(chat_module.router, tags=["chat-module"])
app.include_router(chats_module, tags=["chats-module"])
app.include_router(builder_module.router, tags=["builder-module"])
app.include_router(billing_module, tags=["billing-module"])
app.include_router(admin_module, tags=["admin-module"])
app.include_router(history_module, tags=["history-module"])
app.include_router(bots_module, tags=["bots-module"])
app.include_router(variables_module, tags=["variables-module"])

# WebSockets
app.include_router(websocket_notifications.router, tags=["websocket-notifications"])
app.include_router(websocket_chat.router, prefix="/frontend/chat", tags=["websocket-chat"])
app.include_router(amocrm_router, prefix="/api/amocrm", tags=["amocrm"])

# Модульные статические файлы (монтируем ПЕРВЫМИ - более специфичные маршруты)
modules_dir = Path(__file__).parent / "frontend" / "modules"
for module_path in sorted(modules_dir.iterdir()):
    if module_path.is_dir() and (module_path / "static").exists():
        module_name = module_path.name
        module_static = module_path / "static"
        app.mount(f"/static/{module_name}", StaticFiles(directory=str(module_static)), name=f"static-{module_name}")

# Основные статические файлы (монтируем после модульных)
static_dir = Path(__file__).parent / "frontend" / "shared" / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def root(request: Request):
    """Корневой эндпоинт - главная страница"""
    from app.frontend.pages.public import landing_page
    return await landing_page(request)


@app.get("/health")
async def health():
    """Проверка состояния сервиса"""
    return {"status": "healthy", "database": "connected", "checkpointer": "initialized"}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
        log_level="info",  # Всегда используем INFO уровень, детальные настройки выше
    )
