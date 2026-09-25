"""Жизненный цикл процесса вокруг DI: пулы Oxyde, eager-сборка, lifecycle-ресурсы.

HTTP-фабрика, worker, CLI и тесты входят в один и тот же ``open_di``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TypeVar

from core.config import BaseSettings
from core.db.migration_manifest import database_url_for_migration_key
from core.db.oxyde_runtime import oxyde_databases
from core.di.errors import DiError
from core.di.kit import ProcessIdentity, Recipe, ServiceDi, build_di, process_roots
from core.types import MigrationDatabaseUrlKey

DiT = TypeVar("DiT", bound=ServiceDi)


@asynccontextmanager
async def open_di(
    di_class: type[DiT],
    *,
    settings: BaseSettings,
    identity: ProcessIdentity,
    database: MigrationDatabaseUrlKey,
    lifecycle: tuple[Recipe, ...] = (),
) -> AsyncGenerator[DiT]:
    """Держать базы процесса и собрать его DI; выход закрывает всё в обратном порядке."""
    service_url = database_url_for_migration_key(settings.database, database)
    if service_url is None or service_url == "":
        raise DiError((f"{di_class.__qualname__}: database.{database} is not configured",))
    async with (
        oxyde_databases(default_url=service_url, shared_url=settings.database.shared_url),
        build_di(di_class, roots=process_roots(settings, identity), lifecycle=lifecycle) as di,
    ):
        yield di
