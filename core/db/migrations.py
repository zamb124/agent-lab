"""
Функции для запуска Alembic миграций по всем сервисным БД.

Каждый сервис имеет собственное Alembic-дерево в migrations/<service>/.

Перед вызовом run_migrations_async() реестр должен быть заполнен (см. migrations/services.json
и core.db.migration_manifest.bootstrap_migration_registry).
"""

import asyncio

from alembic import command
from alembic.config import Config
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from core.config.loader import get_project_root
from core.db.migration_manifest import expected_migration_registry_names
from core.db.service_registry import get_all_services, get_service_by_name
from core.logging import get_logger

logger = get_logger(__name__)


def _make_alembic_config(script_location: str, db_url: str) -> Config:
    root = get_project_root()
    ini_path = root / script_location / "alembic.ini"

    if not ini_path.exists():
        raise FileNotFoundError(f"alembic.ini не найден: {ini_path}")

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(root / script_location))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _assert_full_registry() -> None:
    expected = expected_migration_registry_names()
    names = {s.name for s in get_all_services()}
    missing = expected - names
    extra = names - expected
    if missing or extra:
        raise ValueError(
            "Реестр миграций не совпадает с манифестом для текущего конфига: "
            + f"ожидались {sorted(expected)}, в реестре {sorted(names)}. "
            + "Вызовите core.db.migration_manifest.bootstrap_migration_registry() "
            + "или: python -m scripts.db_migrate …"
        )


def run_migrations() -> None:
    asyncio.run(run_migrations_async())


async def run_migrations_async(service: str | None = None) -> None:
    """
    Применяет upgrade head.

    Args:
        service: если задано — только это дерево; иначе все сервисы из реестра.
    """
    _assert_full_registry()

    services = get_all_services()
    if service is not None:
        services = [s for s in services if s.name == service]
        if not services:
            raise ValueError(
                f"Сервис {service!r} не в реестре миграций "
                + "(для optional-сервисов задайте database URL, см. migrations/services.json)"
            )

    for svc in services:
        db_url = svc.get_db_url()
        cfg = _make_alembic_config(svc.alembic_script_location, db_url)

        logger.info(f"Миграция сервиса '{svc.name}' → {db_url[:60]}…")

        engine = create_async_engine(db_url, poolclass=pool.NullPool)
        async with engine.connect() as conn:
            await conn.run_sync(_run_upgrade, cfg)
        await engine.dispose()

        logger.info(f"Миграция '{svc.name}' завершена")


def _run_upgrade(sync_conn: Connection, cfg: Config) -> None:
    cfg.attributes["connection"] = sync_conn
    command.upgrade(cfg, "head")


async def run_downgrade_async(service: str, revision: str) -> None:
    _assert_full_registry()
    svc = get_service_by_name(service)
    db_url = svc.get_db_url()
    cfg = _make_alembic_config(svc.alembic_script_location, db_url)

    engine = create_async_engine(db_url, poolclass=pool.NullPool)
    async with engine.connect() as conn:
        await conn.run_sync(_run_downgrade, cfg, revision)
    await engine.dispose()


def _run_downgrade(sync_conn: Connection, cfg: Config, revision: str) -> None:
    cfg.attributes["connection"] = sync_conn
    command.downgrade(cfg, revision)


async def run_current_async(service: str) -> None:
    _assert_full_registry()
    svc = get_service_by_name(service)
    db_url = svc.get_db_url()
    cfg = _make_alembic_config(svc.alembic_script_location, db_url)

    engine = create_async_engine(db_url, poolclass=pool.NullPool)
    async with engine.connect() as conn:
        await conn.run_sync(_run_current, cfg)
    await engine.dispose()


def _run_current(sync_conn: Connection, cfg: Config) -> None:
    cfg.attributes["connection"] = sync_conn
    command.current(cfg)


def run_history(service: str) -> None:
    _assert_full_registry()
    svc = get_service_by_name(service)
    db_url = svc.get_db_url()
    cfg = _make_alembic_config(svc.alembic_script_location, db_url)
    _ = command.history(cfg)


def run_heads(service: str) -> None:
    _assert_full_registry()
    svc = get_service_by_name(service)
    db_url = svc.get_db_url()
    cfg = _make_alembic_config(svc.alembic_script_location, db_url)
    _ = command.heads(cfg)


def run_revision(service: str, message: str, *, autogenerate: bool) -> None:
    _assert_full_registry()
    svc = get_service_by_name(service)
    db_url = svc.get_db_url()
    cfg = _make_alembic_config(svc.alembic_script_location, db_url)
    _ = command.revision(cfg, message=message, autogenerate=autogenerate)
