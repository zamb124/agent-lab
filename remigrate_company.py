"""
Скрипт для перемиграции компании.
Использование: uv run python remigrate_company.py <company_id>
"""

import asyncio
import sys
import logging

from app.db.repositories import Storage
from app.core.migration import Migrator
from app.identity.models import Company

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def remigrate_company(company_id: str):
    """
    Перемигрирует компанию: все публичные тулы и дефолтные flows.
    
    Args:
        company_id: ID компании для перемиграции
    """
    storage = Storage()
    migrator = Migrator()
    
    company_data = await storage.get(f"company:{company_id}", force_global=True)
    if not company_data:
        raise ValueError(f"Компания {company_id} не найдена")
    
    company = Company.model_validate_json(company_data)
    logger.info(f"Найдена компания: {company.name} ({company.company_id})")
    
    await migrator.migrate_defaults_for_company(company)
    
    logger.info(f"✅ Компания {company_id} успешно перемигрирована")


async def main():
    if len(sys.argv) < 2:
        print("Использование: uv run python remigrate_company.py <company_id>")
        print("Пример: uv run python remigrate_company.py system")
        sys.exit(1)
    
    company_id = sys.argv[1]
    
    try:
        await remigrate_company(company_id)
    except Exception as e:
        logger.error(f"Ошибка перемиграции компании {company_id}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

