"""
Agents Service - FastAPI приложение для управления агентами.

Порт: 8001
БД: agents_db (service) + shared_db
"""

import logging
from fastapi import FastAPI

from core.app import create_service_app
from core.files import initialize_default_processors
from core.clients.payment import PaymentProviderFactory
from apps.agents.config import AgentsSettings
from apps.agents.container import get_agents_container

logger = logging.getLogger(__name__)


async def on_startup(app: FastAPI, container, settings):
    """Кастомная логика при старте"""
    # Инициализация платежных провайдеров
    PaymentProviderFactory.initialize()
    
    # Инициализация файловых процессоров
    initialize_default_processors(
        file_repository=container.file_repository,
        storage=container.storage
    )
    
    # Миграция
    logger.info("Запуск миграции системной компании...")
    migrator = container.migrator
    await migrator.run_full_migration()
    logger.info("Миграция завершена")


# Импорт роутеров
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
from apps.agents.api.v1.variables import router as variables_router


def create_app() -> FastAPI:
    """Создает FastAPI приложение (алиас для совместимости)"""
    return _create_app()


def _create_app() -> FastAPI:
    """Внутренняя функция создания приложения"""
    return create_service_app(
    service_name="agents",
    settings_class=AgentsSettings,
    get_container=get_agents_container,
    routers=[
        agents_router,
        tools_router,
        flows_router,
        tasks_router,
        sessions_router,
        whatsapp_router,
        history_router,
        files_router,
        payments_router,
        fashn_router,
        webhooks_router,
        leads_router,
        variables_router,
    ],
    repository_names=[
        "agent_repository",
        "flow_repository",
        "tool_repository",
        "session_repository",
        "mcp_server_repository",
    ],
    on_startup=on_startup,
    create_tables_config={
        "service": ["storage", "stores", "agent_states", "otel_spans"],
        "shared": ["users", "storage", "variables", "usage"],
    },
    title="Agents Service",
    description="Сервис для управления агентами, flows и tools",
)


app = create_app()
