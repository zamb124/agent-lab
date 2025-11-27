"""
Дебаг скрипт для проверки user и companies
"""
import asyncio
import json
import sys

async def main():
    # Инициализируем settings
    from core.config.loader import load_merged_config
    from core.config import set_settings
    from apps.agents.config import AgentsSettings
    from pathlib import Path
    
    merged_config = load_merged_config(
        base_config_path=Path("conf.json"),
        service_config_path=Path("apps/agents/conf.json")
    )
    settings = AgentsSettings(**merged_config)
    set_settings(settings)
    
    print(f"Settings: env={settings.server.env}, shared_db={settings.database.shared_url}")
    
    # Получаем контейнер
    from apps.agents.container import get_agents_container
    container = get_agents_container()
    
    user_repo = container.user_repository
    print(f"\nuser_repo storage db_url: {user_repo._storage.db_url}")
    
    # Список всех пользователей
    print("\n=== Все пользователи в БД ===")
    users = await user_repo.list_all(limit=10)
    for user in users:
        print(f"  user_id: {user.user_id}")
        print(f"  name: {user.name}")
        print(f"  companies: {user.companies}")
        print(f"  active_company_id: {user.active_company_id}")
        print("  ---")
    
    # Проверяем конкретного пользователя если передан аргумент
    if len(sys.argv) > 1:
        user_id = sys.argv[1]
        print(f"\n=== Проверка пользователя {user_id} ===")
        user = await user_repo.get(user_id)
        if user:
            print(f"  user_id: {user.user_id}")
            print(f"  name: {user.name}")
            print(f"  companies: {user.companies}")
            print(f"  active_company_id: {user.active_company_id}")
        else:
            print(f"  Пользователь {user_id} НЕ НАЙДЕН")
    
    # Проверяем user_providers
    print("\n=== user_providers в БД (глобальные) ===")
    storage = container.shared_storage
    async with storage._get_session() as session:
        from sqlalchemy import text
        result = await session.execute(text("SELECT key, value::text FROM users WHERE key LIKE 'user_providers:%' LIMIT 10"))
        rows = result.fetchall()
        for row in rows:
            val = str(row[1])[:100] if row[1] else "NULL"
            print(f"  {row[0]}: {val}...")
        if not rows:
            print("  (нет записей - user_providers не созданы глобально!)")
    
    print("\n=== user_providers с префиксом company (НЕПРАВИЛЬНЫЕ) ===")
    async with storage._get_session() as session:
        from sqlalchemy import text
        result = await session.execute(text("SELECT key FROM users WHERE key LIKE 'company:%:user_providers:%' LIMIT 10"))
        rows = result.fetchall()
        for row in rows:
            print(f"  {row[0]}")
        if not rows:
            print("  (нет записей - это хорошо!)")

if __name__ == "__main__":
    asyncio.run(main())

