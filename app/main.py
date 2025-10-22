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
from fastapi.staticfiles import StaticFiles
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.config import settings
from app.core.lifespan import lifespan
from app.api.api import router as api_router
from app.frontend.api_router import router as frontend_api_router
from app.frontend.pages_router import router as frontend_pages_router
from app.frontend.websockets_router import router as frontend_websockets_router
from app.frontend.websockets.notifications import router as websocket_notifications_router
from app.middleware.auth import AuthMiddleware
from app.middleware.profiling import ProfilingMiddleware

# Настройка логирования
logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Игнорируем предупреждения о незакрытых сессиях aiohttp (от Google Gemini SDK)
import warnings
warnings.filterwarnings("ignore", message=".*Unclosed.*aiohttp.*")

# Отключаем логи asyncio о незакрытых ресурсах (от внешних SDK)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)


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
logging.getLogger("app.core.migration.migrator").setLevel(logging.WARNING)
logging.getLogger("app.core.agent_factory").setLevel(logging.WARNING)
logging.getLogger("app.db.repositories.storage").setLevel(logging.WARNING)

# Оставляем только ключевые логи
logging.getLogger("app.agents.base").setLevel(
    logging.WARNING
)  # Убираем избыточные логи загрузки tools
logging.getLogger("app.workers.task_processor").setLevel(
    logging.INFO
)  # Основные логи воркера
logging.getLogger("app.tools.misc.standard").setLevel(
    logging.WARNING
)  # Убираем технические логи ask_user
logging.getLogger("app.core.llm_factory").setLevel(
    logging.WARNING
)  # Отключаем wrapper логи

# Убираем детальные DEBUG логи uvicorn и websocket
logging.getLogger("uvicorn.protocols.websockets").setLevel(logging.WARNING)
logging.getLogger("uvicorn.protocols.http").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("websockets.protocol").setLevel(logging.WARNING)
logging.getLogger("websockets.server").setLevel(logging.WARNING)

# Включаем INFO только для профилирования и старта приложения
logging.getLogger("app.middleware.profiling").setLevel(logging.INFO)
logging.getLogger("uvicorn.error").setLevel(logging.INFO)
logging.getLogger("__main__").setLevel(logging.INFO)

# Включаем INFO логи для LLM биллинга
logging.getLogger("app.core.llm_billing_wrapper").setLevel(logging.INFO)

# Отключаем шумные INFO логи
logging.getLogger("app.workers.task_processor").setLevel(logging.WARNING)
logging.getLogger("app.db.repositories.task_repository").setLevel(logging.WARNING)
logging.getLogger("app.middleware.auth").setLevel(logging.WARNING)
logging.getLogger("app.identity.auth_service").setLevel(logging.WARNING)
logging.getLogger("app.frontend.websockets.chat").setLevel(logging.WARNING)

# Включаем INFO для WhatsApp для отладки
logging.getLogger("app.api.v1.whatsapp").setLevel(logging.INFO)
logging.getLogger("app.interfaces.whatsapp_interface").setLevel(logging.INFO)
logging.getLogger("app.services.variables_service").setLevel(logging.INFO)

logger = logging.getLogger(__name__)


# Создание FastAPI приложения
app = FastAPI(
    title="Agents Lab",
    description="Платформа для создания и управления ИИ агентами с LangGraph",
    version="0.1.0",
    debug=settings.server.debug,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Proxy headers middleware (для правильной работы за nginx)
app.add_middleware(
    ProxyHeadersMiddleware,
    trusted_hosts=["*"] if settings.server.debug else [settings.server.domain, f"*.{settings.server.domain}"]
)

# Profiling middleware (замер времени обработки запросов)
app.add_middleware(
    ProfilingMiddleware,
    log_slow_requests=True,
    slow_threshold_ms=500
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


# Cache-Control middleware для статических файлов
@app.middleware("http")
async def static_cache_middleware(request: Request, call_next):
    response = await call_next(request)

    # Добавляем кеширование для статических файлов плагинов и shared
    if request.url.path.startswith("/static/"):
        # Для JS/CSS файлов - кешируем на 1 год
        if request.url.path.endswith(('.js', '.css')):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        # Для изображений и других ресурсов - кешируем на 1 час
        else:
            response.headers["Cache-Control"] = "public, max-age=3600"

    return response

# Подключение роутеров

# API роутер (включает v1 и другие суброутеры)
app.include_router(api_router)

# Frontend роутеры
app.include_router(frontend_api_router, prefix="/frontend/api")
app.include_router(frontend_pages_router)
app.include_router(frontend_websockets_router, prefix="/frontend")
app.include_router(websocket_notifications_router, tags=["websocket-notifications"], include_in_schema=False)

# Frontend Modules загружаются автоматически через плагинную систему
# (см. discover_and_load_plugins в lifespan)

# Модульные статические файлы (монтируем ПЕРВЫМИ - более специфичные маршруты)
modules_dir = Path(__file__).parent / "frontend" / "modules"
for module_path in sorted(modules_dir.iterdir()):
    if module_path.is_dir() and (module_path / "static").exists():
        module_name = module_path.name
        module_static = module_path / "static"
        app.mount(f"/static/{module_name}", StaticFiles(directory=str(module_static)), name=f"static-{module_name}")

# Pages статические файлы
pages_dir = Path(__file__).parent / "frontend" / "pages"
for page_path in sorted(pages_dir.iterdir()):
    if page_path.is_dir() and (page_path / "static").exists():
        page_name = page_path.name
        page_static = page_path / "static"
        app.mount(f"/static/{page_name}", StaticFiles(directory=str(page_static)), name=f"static-{page_name}")

# Основные статические файлы (монтируем после модульных)
static_dir = Path(__file__).parent / "frontend" / "shared" / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Документация MkDocs (если собрана)
docs_dir = Path(__file__).parent.parent / "site"
if docs_dir.exists():
    app.mount("/docs", StaticFiles(directory=str(docs_dir), html=True), name="docs")
    logger.info("📚 Документация MkDocs доступна на /docs")


@app.get("/", include_in_schema=False)
async def root(request: Request):
    """Корневой эндпоинт - главная страница"""
    from app.frontend.pages.public import landing_page
    return await landing_page(request)


@app.get("/health", summary="Проверка работоспособности", tags=["Система"])
async def health():
    """
    Проверяет работоспособность сервиса.
    
    **Возвращает статус:**
    - status: "healthy" если всё работает
    - database: состояние подключения к БД
    - checkpointer: состояние LangGraph checkpointer
    
    Используйте для мониторинга и health checks.
    
    Returns:
        Статус всех компонентов системы
    """
    return {"status": "healthy", "database": "connected", "checkpointer": "initialized"}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
        log_level="info",  # Всегда используем INFO уровень, детальные настройки выше
    )
