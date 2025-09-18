#!/usr/bin/env python3
"""
Скрипт очистки БД от записей без префикса компании.
Удаляет старые agent:, flow:, task:, session: записи которые должны быть в компаниях.
"""

import asyncio
import sys
from pathlib import Path

# Добавляем путь к приложению
sys.path.append(str(Path(__file__).parent))

from app.db.database import AsyncSessionLocal
from app.db.models import Storage as StorageModel
from sqlalchemy import select, delete


async def cleanup_non_company_data():
    """Удаляет все записи без префикса компании"""
    
    async with AsyncSessionLocal() as session:
        print("🔍 Ищем записи без префикса компании...")
        
        # Получаем все ключи
        result = await session.execute(select(StorageModel.key))
        all_keys = [row.key for row in result]
        
        print(f"📊 Всего записей в БД: {len(all_keys)}")
        
        # Ключи которые должны остаться (глобальные)
        global_prefixes = [
            'user:', 'company:', 'subdomain:', 
            'auth_session:', 'auth_state:', 'token:'
        ]
        
        # Ключи которые должны быть удалены (старые без компании)
        old_prefixes = [
            'agent:', 'flow:', 'task:', 'session:', 'tool:'
        ]
        
        keys_to_delete = []
        
        for key in all_keys:
            # Пропускаем глобальные ключи
            if any(key.startswith(prefix) for prefix in global_prefixes):
                continue
                
            # Пропускаем ключи уже в компаниях
            if key.startswith('company:') and ':' in key[8:]:
                continue
                
            # Удаляем старые ключи без компании
            if any(key.startswith(prefix) for prefix in old_prefixes):
                keys_to_delete.append(key)
        
        print(f"🗑️  Найдено {len(keys_to_delete)} записей для удаления:")
        
        for key in keys_to_delete:
            print(f"  - {key}")
        
        if keys_to_delete:
            confirm = input(f"\n❓ Удалить {len(keys_to_delete)} записей? (y/N): ")
            
            if confirm.lower() == 'y':
                # Удаляем записи
                for key in keys_to_delete:
                    await session.execute(delete(StorageModel).where(StorageModel.key == key))
                
                await session.commit()
                print(f"✅ Удалено {len(keys_to_delete)} записей")
            else:
                print("❌ Операция отменена")
        else:
            print("✅ Нет записей для удаления")


if __name__ == "__main__":
    print("🧹 Скрипт очистки БД от записей без префикса компании")
    print("=" * 50)
    
    try:
        asyncio.run(cleanup_non_company_data())
    except KeyboardInterrupt:
        print("\n❌ Операция прервана пользователем")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)
    
    print("✅ Скрипт завершен")
