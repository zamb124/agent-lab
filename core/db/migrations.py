"""
Функции для запуска Alembic миграций.

Используется для автоматического запуска миграций при старте сервиса в dev режиме.
Поддерживает multi-db через service_registry.
"""

import logging
from pathlib import Path

from alembic.config import Config
from alembic import command

logger = logging.getLogger(__name__)


def _get_alembic_config(migration_path: str = "migrations") -> Config | None:
    """
    Создает конфигурацию Alembic.
    
    Args:
        migration_path: Путь к директории с миграциями
        
    Returns:
        Config или None если alembic.ini не найден
    """
    project_root = Path(__file__).parent.parent.parent
    alembic_ini_path = project_root / migration_path / "alembic.ini"
    
    if not alembic_ini_path.exists():
        logger.warning(f"alembic.ini not found at {alembic_ini_path}")
        return None
    
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("script_location", str(project_root / migration_path))
    
    return alembic_cfg


def run_migrations(migration_path: str = "migrations") -> None:
    """
    Запускает все pending миграции (синхронно через asyncio.run).
    
    Использовать при запуске из sync контекста (CLI, Makefile).
    Итерируется по всем уникальным БД из service_registry.
    
    Args:
        migration_path: Путь к директории с миграциями
    """
    alembic_cfg = _get_alembic_config(migration_path)
    if not alembic_cfg:
        return
    
    logger.info(f"Running migrations from {migration_path}...")
    command.upgrade(alembic_cfg, "head")
    logger.info("Migrations completed")


async def run_migrations_async(migration_path: str = "migrations") -> None:
    """
    Запускает все pending миграции (асинхронно).
    
    Использовать при запуске из async контекста (FastAPI lifespan, pytest-asyncio).
    Итерируется по всем уникальным БД из service_registry.
    Передает connection через cfg.attributes чтобы избежать asyncio.run() внутри event loop.
    
    Args:
        migration_path: Путь к директории с миграциями
    """
    from sqlalchemy import pool
    from sqlalchemy.ext.asyncio import create_async_engine
    from core.db.service_registry import get_unique_db_urls
    
    alembic_cfg = _get_alembic_config(migration_path)
    if not alembic_cfg:
        return
    
    db_urls = get_unique_db_urls()
    
    if not db_urls:
        logger.warning("No database URLs registered, skipping migrations")
        return
    
    logger.info(f"Running async migrations from {migration_path}...")
    
    for db_url, services in db_urls.items():
        logger.info(f"Migrating DB for services: {services}")
        
        engine = create_async_engine(db_url, poolclass=pool.NullPool)
        
        async with engine.begin() as conn:
            await conn.run_sync(_run_upgrade_with_connection, alembic_cfg)
        
        await engine.dispose()
        
        logger.info(f"Migrations completed for: {services}")


def _run_upgrade_with_connection(connection, alembic_cfg: Config) -> None:
    """
    Запускает upgrade передавая connection через attributes.
    
    Args:
        connection: SQLAlchemy connection
        alembic_cfg: Alembic Config
    """
    alembic_cfg.attributes["connection"] = connection
    command.upgrade(alembic_cfg, "head")


def get_current_revision(migration_path: str = "migrations") -> str | None:
    """
    Возвращает текущую версию миграции.
    
    Args:
        migration_path: Путь к директории с миграциями
        
    Returns:
        ID текущей ревизии или None если миграции не применялись
    """
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine
    from core.db.service_registry import get_unique_db_urls
    
    alembic_cfg = _get_alembic_config(migration_path)
    if not alembic_cfg:
        return None
    
    script = ScriptDirectory.from_config(alembic_cfg)
    
    # Берем первую БД из реестра
    db_urls = get_unique_db_urls()
    if not db_urls:
        return None
    
    db_url = list(db_urls.keys())[0]
    sync_url = db_url.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        return ctx.get_current_revision()


def get_pending_migrations(migration_path: str = "migrations") -> list[str]:
    """
    Возвращает список pending миграций.
    
    Args:
        migration_path: Путь к директории с миграциями
        
    Returns:
        Список ID ревизий которые ещё не применены
    """
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine
    from core.db.service_registry import get_unique_db_urls
    
    alembic_cfg = _get_alembic_config(migration_path)
    if not alembic_cfg:
        return []
    
    script = ScriptDirectory.from_config(alembic_cfg)
    
    # Берем первую БД из реестра
    db_urls = get_unique_db_urls()
    if not db_urls:
        return []
    
    db_url = list(db_urls.keys())[0]
    sync_url = db_url.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        current = ctx.get_current_revision()
        
    pending = []
    for rev in script.walk_revisions():
        if current is None or rev.revision != current:
            pending.append(rev.revision)
        if rev.revision == current:
            break
            
    return pending


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    run_migrations()
