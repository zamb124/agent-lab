"""
Накат ``0001_initial`` на тестовые базы.

Вызывается из ``make test-up`` до старта стека. pytest миграции не применяет:
``setup_database_before_tests`` только проверяет запись ``0001_initial``.

База со старыми таблицами и без этой записи не накатывается: её удаляют и
поднимают пустой. Сид компании ``system`` нужен до старта сервисов.
"""

from __future__ import annotations

import asyncio
import os
import sys

from tests.fixtures.test_database_env import TEST_DATABASE_ENV

for _env_key, _env_value in TEST_DATABASE_ENV.items():
    _ = os.environ.setdefault(_env_key, _env_value)
_ = os.environ.setdefault("TESTING", "true")

from core.db.postgres_service_databases import (  # noqa: E402
    ensure_postgres_service_databases_async,
)


async def _seed_system_company() -> None:
    from core.identity.system_bootstrap import ensure_system_company_exists

    _ = await ensure_system_company_exists()


async def _run() -> int:
    from core.db.migration_manifest import bootstrap_migration_registry
    from core.db.migrations import run_migrations_async

    shared_db_url = os.environ["DATABASE__SHARED_URL"]
    await ensure_postgres_service_databases_async(reference_shared_url=shared_db_url)

    bootstrap_migration_registry()
    await run_migrations_async()
    await _seed_system_company()
    print("test_migrate: 0001_initial применён, компания system есть")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
