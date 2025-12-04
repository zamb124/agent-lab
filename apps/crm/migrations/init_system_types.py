"""
Инициализация системных типов сущностей.

Запускается автоматически при старте CRM сервиса.
"""

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def init_system_types():
    """
    Инициализирует системные типы сущностей.
    
    Вызывается из lifespan при старте приложения.
    """
    from apps.crm.container import get_crm_container
    
    container = get_crm_container()
    entity_type_service = container.entity_type_service
    
    created = await entity_type_service.init_system_types()
    
    if created:
        logger.info(f"Создано {len(created)} системных типов: {[t.type_id for t in created]}")
    else:
        logger.info("Системные типы уже существуют")


async def main():
    """CLI для ручного запуска миграции"""
    from core.config.loader import load_merged_config
    from core.config import set_settings
    from apps.crm.config import CRMSettings
    from apps.crm.container import CRMContainer, set_crm_container
    
    merged_config = load_merged_config(
        base_config_path=Path("conf.json"),
        service_config_path=Path(__file__).parent.parent / "conf.json"
    )
    
    settings = CRMSettings(**merged_config)
    set_settings(settings)
    
    container = CRMContainer(
        db_url=settings.database.url,
        shared_db_url=settings.database.shared_url
    )
    set_crm_container(container)
    
    await container.init_db()
    
    await init_system_types()


if __name__ == "__main__":
    asyncio.run(main())

