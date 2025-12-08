#!/usr/bin/env python
"""
Скрипт для отладки миграции CRM flow и агента.
Запуск: uv run python scripts/debug_crm_flow_migration.py
"""

import asyncio
import sys
import os
sys.path.insert(0, ".")

# Проверяем тестовые переменные
print("ENV check:")
print(f"  PYTEST_CURRENT_TEST = {os.environ.get('PYTEST_CURRENT_TEST', 'NOT SET')}")
print(f"  _PYTEST_RAISE = {os.environ.get('_PYTEST_RAISE', 'NOT SET')}")

async def main():
    from apps.agents.container import get_agents_container
    from apps.agents.models import FlowConfig
    from core.context import Context, set_context
    from core.models import User, Company
    
    print("=" * 60)
    print("DEBUG: CRM Flow Migration")
    print("=" * 60)
    
    # Инициализация контейнера
    container = get_agents_container()
    
    # Устанавливаем контекст компании sss (как при реальном запросе)
    sss_company = Company(company_id="sss", name="SSS")
    sss_user = User(user_id="user_84c1cff0ea3e", username="zambas124", name="Test User")
    context = Context(user=sss_user, active_company=sss_company, platform="api")
    set_context(context)
    print(f"\n1. Контекст установлен: company={sss_company.company_id}")
    
    # Проверяем flow в репозитории
    flow_repo = container.flow_repository
    flow_id = "crm_entity_extractor"
    flow = await flow_repo.get(flow_id)
    print(f"\n2. Flow '{flow_id}' в БД: {flow is not None}")
    if flow:
        print(f"   - entry_point_agent: {flow.entry_point_agent}")
    
    # Проверяем агента в репозитории
    agent_repo = container.agent_repository
    agent_id = "apps.agents.agents.crm.entity_extractor_agent.EntityExtractorAgent"
    agent = await agent_repo.get(agent_id)
    print(f"\n3. Агент '{agent_id}' в БД: {agent is not None}")
    
    # Пробуем мигрировать
    print("\n4. Запускаем миграцию flow...")
    migrator = container.migrator
    config_path = "apps.agents.flows.crm_entity_extractor_flow.crm_entity_extractor_flow_config"
    
    try:
        flow_config = await FlowConfig.migrate(
            flow_id=config_path,
            migrator=migrator,
            with_dependencies=True
        )
        print(f"   Миграция завершена: flow_id={flow_config.flow_id}")
    except Exception as e:
        print(f"   ОШИБКА миграции: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Проверяем flow после миграции
    flow_after = await flow_repo.get(flow_id)
    print(f"\n5. Flow после миграции: {flow_after is not None}")
    
    # Проверяем агента после миграции
    agent_after = await agent_repo.get(agent_id)
    print(f"\n6. Агент после миграции: {agent_after is not None}")
    if agent_after:
        print(f"   - agent_id: {agent_after.agent_id}")
        print(f"   - name: {agent_after.name}")
    
    # Пробуем создать агента через фабрику
    print("\n7. Пробуем получить агента через AgentFactory...")
    agent_factory = container.agent_factory
    try:
        agent_instance = await agent_factory.get_agent(agent_id)
        print(f"   Агент создан: {agent_instance}")
    except Exception as e:
        print(f"   ОШИБКА: {e}")
    
    # Проверяем какой LLM используется
    print("\n8. Проверяем LLM...")
    from core.clients.llm.factory import get_llm
    llm = get_llm()
    print(f"   LLM тип: {type(llm).__name__}")
    print(f"   LLM: {llm}")
    
    print("\n" + "=" * 60)
    print("DEBUG ЗАВЕРШЕН")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())

