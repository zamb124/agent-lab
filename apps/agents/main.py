"""
Agents Service - FastAPI приложение для управления агентами.

Порт: 8001
БД: agents_db (service) + shared_db
"""

import logging
from pathlib import Path
from fastapi import FastAPI
from contextlib import asynccontextmanager

from core.config.loader import load_merged_config
from core.logging import setup_logging
from core.db import create_tables
from core.container import set_system_container
from apps.agents.config import AgentsSettings
from apps.agents.container import AgentsContainer, set_agents_container

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan события для FastAPI"""
    logger.info("Запуск Agents Service...")
    
    container = app.state.container
    
    logger.info("Создание таблиц в service БД...")
    await create_tables(
        db_url=container.db_url,
        table_names=["storage", "stores", "agent_states", "otel_spans"]
    )
    
    if container.shared_db_url:
        logger.info("Создание таблиц в shared БД...")
        await create_tables(
            db_url=container.shared_db_url,
            table_names=["users", "tasks", "storage", "variables"]
        )
    
    logger.info("Запуск миграции системной компании...")
    migrator = container.migrator
    await migrator.run_full_migration()
    logger.info("Миграция завершена")
    
    logger.info("Agents Service запущен")
    
    yield
    
    logger.info("Остановка Agents Service...")


def create_app() -> FastAPI:
    """Создает FastAPI приложение"""
    
    project_root = Path(__file__).parent.parent.parent
    service_config_path = Path(__file__).parent / "conf.json"
    
    merged_config = load_merged_config(
        base_config_path=project_root / "conf.json",
        service_config_path=service_config_path
    )
    
    settings = AgentsSettings(**merged_config)
    
    setup_logging("agents", settings.logging)
    
    container = AgentsContainer(
        service_db_url=settings.database.url,
        shared_db_url=settings.database.shared_url
    )
    set_agents_container(container)
    set_system_container(container)
    
    app = FastAPI(
        title="Agents Service",
        version="1.0.0",
        description="Сервис для управления агентами, flows и tools",
        lifespan=lifespan
    )
    
    app.state.container = container
    app.state.settings = settings
    
    logger.info("Подключение роутеров...")
    
    from apps.agents.api.v1.agents import router as agents_router
    from apps.agents.api.v1.tools import router as tools_router
    from apps.agents.api.v1.flows import router as flows_router
    from apps.agents.api.v1.tasks import router as tasks_router
    from apps.agents.api.v1.sessions import router as sessions_router
    from apps.agents.api.v1.whatsapp import router as whatsapp_router
    from apps.agents.api.v1.history import router as history_router
    from apps.agents.api.v1.files import router as files_router
    from apps.agents.api.v1.payments import router as payments_router
    from apps.agents.api.v1.fashn import router as fashn_router
    from apps.agents.api.v1.webhooks import router as webhooks_router
    from apps.agents.api.v1.leads import router as leads_router
    from apps.agents.api.v1.knowledge_base import router as kb_router
    
    app.include_router(agents_router, prefix="/agents/api/v1", tags=["agents"])
    app.include_router(tools_router, prefix="/agents/api/v1", tags=["tools"])
    app.include_router(flows_router, prefix="/agents/api/v1", tags=["flows"])
    app.include_router(tasks_router, prefix="/agents/api/v1", tags=["tasks"])
    app.include_router(sessions_router, prefix="/agents/api/v1", tags=["sessions"])
    app.include_router(whatsapp_router, prefix="/agents/api/v1", tags=["whatsapp"])
    app.include_router(history_router, prefix="/agents/api/v1", tags=["history"])
    app.include_router(files_router, prefix="/agents/api/v1", tags=["files"])
    app.include_router(payments_router, prefix="/agents/api/v1", tags=["payments"])
    app.include_router(fashn_router, prefix="/agents/api/v1", tags=["fashn"])
    app.include_router(webhooks_router, prefix="/agents/api/v1", tags=["webhooks"])
    app.include_router(leads_router, prefix="/agents/api/v1", tags=["leads"])
    app.include_router(kb_router, prefix="/agents/api/v1", tags=["knowledge-base"])
    
    logger.info("Agents Service создан")
    
    return app


app = create_app()


@app.get("/health")
@app.get("/agents/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "agents"}


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "agents",
        "version": "1.0.0",
        "status": "running"
    }

