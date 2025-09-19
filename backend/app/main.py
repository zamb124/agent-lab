"""
Главная точка входа FastAPI приложения.
"""

# КРИТИЧНО: Monkey patches ДОЛЖНЫ быть применены ДО импорта моделей!
import app.frontend.field_extensions

import logging
import asyncio
import json
import re
import uvicorn
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.checkpointer import init_checkpointer, close_checkpointer
from app.db.database import create_tables, close_db
from app.core.migrator import Migrator
from app.api.v1 import webhooks, admin, telegram, tokens, auth, flows, fashn, files, leads
from app.frontend.api import models as frontend_models
from app.frontend.api import pages as frontend_pages
from app.frontend.api import websocket as frontend_websocket
from app.frontend.main.api import pages as main_pages
from app.frontend.chat.api import router as chat_router
from app.frontend.chat.api import websocket as chat_websocket
from app.middleware.auth import AuthMiddleware
from app.services.cleanup_service import CleanupService

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
                        pretty_json = json.dumps(json_obj, indent=4, ensure_ascii=False)
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
        logger.info("🧹 Запуск периодической очистки истекших данных...")
        asyncio.create_task(_periodic_cleanup())
        logger.info("✅ Периодическая очистка запущена")

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

            # Воркер задач остановится автоматически при завершении приложения

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

# Подключение роутеров
app.include_router(webhooks.router, prefix="/api/v1", tags=["webhooks"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(telegram.router, prefix="/api/v1", tags=["telegram"])
app.include_router(tokens.router, prefix="/api/v1", tags=["tokens"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(flows.router, prefix="/api/v1/flows", tags=["flows"])
app.include_router(fashn.router, prefix="/api/v1/fashn", tags=["fashn"])
app.include_router(files.router, prefix="/api/v1/files", tags=["files"])
app.include_router(leads.router, prefix="/api/v1", tags=["leads"])
app.include_router(frontend_models.router, tags=["frontend"])
app.include_router(frontend_pages.router, tags=["frontend-pages"])
app.include_router(frontend_websocket.router, tags=["frontend-websocket"])
app.include_router(main_pages.router, tags=["main-pages"])
app.include_router(chat_router.router, prefix="/frontend/chat", tags=["chat"])
app.include_router(
    chat_websocket.router, prefix="/frontend/chat", tags=["chat-websocket"]
)

# Статические файлы
static_dir = Path(__file__).parent / "frontend" / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def root(request: Request):
    """Корневой эндпоинт - главная страница"""
    from app.frontend.main.api.pages import landing_page
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
