"""
CRM Service - FastAPI приложение для управления CRM.

Порт: 8003
БД: crm_db (service) + shared_db
"""

import logging

from fastapi import FastAPI

from core.app import create_service_app
from apps.crm.config import CRMSettings
from apps.crm.container import get_crm_container

logger = logging.getLogger(__name__)


async def on_startup(app: FastAPI, container, settings):
    """Кастомная логика при старте"""
    # Инициализация CRM БД (создание таблиц)
    await container.init_db()
    
    # Инициализация системных типов сущностей
    await container.entity_type_service.init_system_types()
    
    logger.info("CRM системные типы инициализированы")


# Импорт роутера (собирает все под-роутеры)
from apps.crm.api.v1.router import router as api_router


def create_app() -> FastAPI:
    """Создает FastAPI приложение"""
    return create_service_app(
        service_name="crm",
        settings_class=CRMSettings,
        get_container=get_crm_container,
        routers=[api_router],
        on_startup=on_startup,
        # CRM использует свою отдельную БД crm_db, таблицы создаются через init_db
        create_tables_config={
            "shared": ["users", "storage"],
        },
        title="CRM Service",
        description="API для управления CRM: сущности, заметки, задачи, связи",
        include_crud_routers=False,  # CRM не использует автоматические CRUD роутеры
        include_broker=False,  # CRM пока не использует TaskIQ
    )


app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    from core.config import get_settings
    settings = get_settings()
    
    uvicorn.run(
        "apps.crm.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=True
    )
