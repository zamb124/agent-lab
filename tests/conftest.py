"""
Простая конфигурация для pytest.
"""
import pytest
import asyncio
import os
import sys
from pathlib import Path

# Добавляем backend в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Загружаем .env файл для тестов
env_file = Path(__file__).parent.parent / "backend" / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)
    print(f"✅ Загружен .env файл: {env_file}")
else:
    print(f"❌ .env файл не найден: {env_file}")

# Настройка переменных окружения для тестов
os.environ["DATABASE__URL"] = "postgresql+asyncpg://agent_user:agent_password@localhost:5436/agent_platform"
os.environ["DATABASE__CHECKPOINTER_URL"] = "postgresql://agent_user:agent_password@localhost:5436/agent_platform"
os.environ["SERVER__DEBUG"] = "true"
# Используем mock LLM по умолчанию для всех тестов
os.environ["LLM__DEFAULT_PROVIDER"] = "mock"
# Настройка S3 для тестов с реальными кредами Yandex
os.environ["S3__ENABLED"] = "true"
os.environ["S3__DEFAULT_BUCKET"] = "vkbucket"


@pytest.fixture(autouse=True, scope="function")
def cleanup_async_resources():
    """Очистка async ресурсов между тестами"""
    yield
    
    # Принудительная очистка после каждого теста
    try:
        import asyncio
        import gc
        
        # Получаем текущий loop
        try:
            loop = asyncio.get_running_loop()
            # Отменяем все pending tasks
            pending = asyncio.all_tasks(loop)
            for task in pending:
                if not task.done():
                    task.cancel()
        except RuntimeError:
            # Нет running loop
            pass
        
        # Принудительный garbage collection
        gc.collect()
        
        # Очистка SQLAlchemy connections
        try:
            from app.db.database import engine
            if hasattr(engine, 'pool'):
                engine.pool.dispose()
        except Exception:
            pass
        
            
    except Exception as e:
        print(f"⚠️ Ошибка очистки ресурсов: {e}")




@pytest.fixture
async def client():
    """HTTP клиент для тестирования API"""
    import httpx
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        yield client