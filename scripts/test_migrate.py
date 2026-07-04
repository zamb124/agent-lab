"""
Применение Alembic-миграций всех сервисных деревьев к тестовым БД.

Вызывается из `make test-up` до старта стека сервисов (`scripts.test_stack up`).
pytest миграции не применяет: фикстура `setup_database_before_tests` только
проверяет, что head в коде совпадает с current в БД, и падает с подсказкой
выполнить `make test-up`.

Логика:
  - CREATE DATABASE для баз, которых нет в init.sql (tracing/worktracker/secrets);
  - если shared-БД пуста (нет alembic_version) — полный прогон всех деревьев;
  - иначе — инкрементальный upgrade только отставших сервисов;
  - сид system-компании: db_test_reset делает TRUNCATE, а crm при старте требует
    существующую company "system" (стек стартует параллельно, ждать frontend нельзя).
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from tests.fixtures.test_database_env import TEST_DATABASE_ENV

for _env_key, _env_value in TEST_DATABASE_ENV.items():
    os.environ.setdefault(_env_key, _env_value)
os.environ.setdefault("TESTING", "true")

from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent

_EXTRA_DATABASES = ("platform_tracing", "platform_worktracker", "platform_secrets")


def _alembic_head_revision(script_location: str) -> str | None:
    ini_path = _REPO_ROOT / script_location / "alembic.ini"
    if not ini_path.exists():
        return None
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(_REPO_ROOT / script_location))
    directory = ScriptDirectory.from_config(cfg)
    heads = directory.get_heads()
    return heads[0] if heads else None


async def _alembic_current_revision(db_url: str) -> str | None:
    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.begin() as conn:
            row = await conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
            first = row.first()
            return first[0] if first else None
    except Exception:
        return None
    finally:
        await engine.dispose()


async def _ensure_postgres_database(admin_url: str, database_name: str) -> None:
    engine = create_async_engine(admin_url, echo=False, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        existing = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": database_name}
        )
        if existing.first() is None:
            await conn.execute(text(f'CREATE DATABASE "{database_name}"'))
    await engine.dispose()


async def _stale_services() -> list[str]:
    from core.config import get_settings
    from core.db.migration_manifest import (
        database_url_for_migration_key,
        load_migration_manifest,
        migration_entry_is_active,
    )

    manifest = load_migration_manifest()
    stale: list[str] = []
    for entry in manifest.services:
        if not migration_entry_is_active(entry):
            continue
        head = _alembic_head_revision(f"migrations/{entry.name}")
        if head is None:
            continue
        db_url = database_url_for_migration_key(get_settings().database, entry.database_url_key)
        if not db_url or not str(db_url).strip():
            continue
        current = await _alembic_current_revision(str(db_url))
        if current != head:
            stale.append(entry.name)
    return stale


async def _seed_system_company() -> None:
    from core.db.repositories.company_repository import CompanyRepository
    from core.db.repositories.subdomain_repository import SubdomainRepository
    from core.db.storage import Storage
    from core.identity.system_bootstrap import ensure_system_company_exists

    shared_storage = Storage(db_url=os.environ["DATABASE__SHARED_URL"])
    _ = await ensure_system_company_exists(
        company_repository=CompanyRepository(storage=shared_storage),
        subdomain_repository=SubdomainRepository(storage=shared_storage),
    )


async def _run() -> int:
    from core.db.migration_manifest import bootstrap_migration_registry
    from core.db.migrations import run_migrations_async

    shared_db_url = os.environ["DATABASE__SHARED_URL"]
    admin_url = shared_db_url.rsplit("/", 1)[0] + "/postgres"
    for database_name in _EXTRA_DATABASES:
        await _ensure_postgres_database(admin_url, database_name)

    bootstrap_migration_registry()
    stale = await _stale_services()
    if not stale:
        await _seed_system_company()
        print("test_migrate: все миграции актуальны")
        return 0

    shared_current = await _alembic_current_revision(shared_db_url)
    if shared_current is None:
        print("test_migrate: shared-БД пуста, полный прогон всех деревьев миграций...")
        await run_migrations_async()
        await _seed_system_company()
        print("test_migrate: миграции применены")
        return 0

    for service_name in stale:
        print(f"test_migrate: upgrade {service_name}...")
        await run_migrations_async(service=service_name)
    await _seed_system_company()
    print(f"test_migrate: применены миграции {len(stale)} сервисов: {', '.join(stale)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
