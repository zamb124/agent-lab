#!/usr/bin/env python3
"""
Скрипт для создания системной компании.
Создает компанию с company_id="system" и системного пользователя.
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from core.logging import setup_logging
from apps.agents.config import get_agents_settings
from apps.agents.container import get_agents_container
from core.models import Company, User, UserStatus, AuthProvider
from core.db.repositories.subdomain_repository import SubdomainMapping

async def create_system_company():
    """Создает системную компанию и пользователя"""

    # Загружаем настройки
    settings = get_agents_settings()

    # Настройка логирования
    setup_logging("create_system_company", settings.logging)

    print("🚀 Создание системной компании...\n")

    # Получаем контейнер
    container = get_agents_container()
    
    # Проверяем shared_db_url
    print(f"📊 Используется shared_db_url: {container.shared_db_url}")
    
    company_repo = container.company_repository
    subdomain_repo = container.subdomain_repository
    user_repo = container.user_repository
    
    # Проверяем, существует ли уже системная компания
    print("🔍 Проверка существования системной компании...")
    system_company = await company_repo.get("system")
    if system_company:
        print(f"✅ Системная компания уже существует: {system_company.company_id}")
        print(f"   Название: {system_company.name}")
        print(f"   Субдомен: {system_company.subdomain}")
        return
    print("ℹ️  Системная компания не найдена, создаем...")

    # Создаем системную компанию
    print("📝 Создание системной компании...")
    system_company = Company(
        company_id="system",
        subdomain="system",
        name="System Company",
        status="active"
    )

    await company_repo.set(system_company)
    print(f"✅ Создана компания: {system_company.company_id}")

    # Создаем маппинг субдомена
    print("📝 Создание маппинга субдомена...")
    subdomain_mapping = SubdomainMapping(subdomain="system", company_id="system")
    await subdomain_repo.set(subdomain_mapping)
    print(f"✅ Создан маппинг: system -> system")

    # Создаем системного пользователя
    print("📝 Создание системного пользователя...")
    existing_user = await user_repo.get("system_migrator")
    if existing_user:
        print("✅ Системный пользователь уже существует")
    else:
        system_user = User(
            user_id="system_migrator",
            provider=AuthProvider.YANDEX,
            provider_user_id="system_migrator",
            email="system@humanitec.ru",
            name="System Migrator",
            status=UserStatus.ACTIVE,
            groups=["system", "admin"],
            companies={"system": ["admin"]},
            active_company_id="system"
        )
        await user_repo.set(system_user)
        print(f"✅ Создан пользователь: {system_user.user_id}")

    print("\n✅ Системная компания успешно создана!")

if __name__ == "__main__":
    try:
        asyncio.run(create_system_company())
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

