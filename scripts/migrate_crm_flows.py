"""
Скрипт для миграции CRM flows в компанию.
"""
import asyncio
import sys
sys.path.insert(0, "/Users/viktor-shved/PycharmProjects/agent-lab")

from apps.agents.container import get_agents_container
from apps.agents.services.migration.migrator import Migrator


async def main():
    print("Инициализация...")
    
    container = get_agents_container()
    migrator = Migrator()
    
    company_repo = container.company_repository
    company = await company_repo.get("fff")
    
    if not company:
        print("Компания fff не найдена!")
        return
    
    print(f"Найдена компания: {company.name} ({company.company_id})")
    
    flows_to_migrate = [
        "apps.agents.flows.crm_entity_extractor_flow.crm_entity_extractor_flow_config",
        "apps.agents.flows.crm_entity_extractor_flow.crm_entity_comparison_flow_config"
    ]
    
    print(f"Миграция {len(flows_to_migrate)} flows...")
    
    await migrator.migrate_for_company(
        company,
        flows=flows_to_migrate,
        with_dependencies=True
    )
    
    print("Миграция завершена!")


if __name__ == "__main__":
    asyncio.run(main())
