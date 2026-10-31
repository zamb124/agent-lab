"""Подключение процессов к базам Oxyde.

У процесса алиас ``default`` — его собственная база, алиас ``shared`` — ``platform_shared``.
Именованный алиас открывается на старте, когда его URL совпадает с одной из этих двух баз.
Алиас ``tracing`` открывается всегда, когда задан ``tracing_url``: спаны пишут все процессы.
Остальные алиасы открывает первый запрос к модели. Накат миграций открывает все заданные URL.

Пулы — ресурс процесса: ``oxyde_databases`` держит их, пока жив хотя бы один владелец.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import oxyde.db.transaction as oxyde_transaction
import oxyde.queries.base as oxyde_query_base
import oxyde.queries.mixins.mutation as oxyde_mutation
from oxyde import PoolSettings, db
from oxyde.db.pool import AsyncDatabase
from oxyde.db.registry import get_connection

from core.config import get_settings
from core.logging import get_logger
from core.models.database_alias import configure_oxyde_aliases, ensure_oxyde_alias

logger = get_logger(__name__)

_holders = 0
_held_shared_url: str | None = None


def _install_alias_opener() -> None:
    if get_connection.__name__ == "_open_alias_then_get":
        return

    async def _open_alias_then_get(
        name: str = "default",
        *,
        ensure_connected: bool = True,
    ) -> AsyncDatabase:
        if name != "default":
            await ensure_oxyde_alias(name)
        return await get_connection(name, ensure_connected=ensure_connected)

    # Копии get_connection снимаются при импорте модулей Oxyde и не входят в __all__.
    oxyde_transaction.get_connection = _open_alias_then_get  # pyright: ignore[reportPrivateImportUsage]
    oxyde_query_base.get_connection = _open_alias_then_get  # pyright: ignore[reportPrivateImportUsage]
    oxyde_mutation.get_connection = _open_alias_then_get  # pyright: ignore[reportPrivateImportUsage]


_install_alias_opener()


async def init_oxyde_databases(
    *,
    default_url: str | None,
    shared_url: str | None,
    all_aliases: bool = False,
) -> None:
    """Открыть пулы ``default`` и ``shared``. Повторный вызов закрывает прежние пулы.

    Именованный алиас открывается, если его URL совпадает с базой процесса или с shared.
    ``all_aliases=True`` открывает все заданные URL: так делает накат миграций.
    """
    if shared_url is None or shared_url == "":
        raise RuntimeError("shared database URL is required")
    service_url = default_url if default_url is not None and default_url != "" else shared_url
    settings = get_settings()
    pool = PoolSettings(
        max_connections=settings.database.pool_max_connections,
        acquire_timeout=settings.database.pool_acquire_timeout_seconds,
    )
    await db.close()
    databases: dict[str, str] = {"default": service_url, "shared": shared_url}
    flows_url = settings.database.flows_url
    tracing_url = settings.database.tracing_url
    rag_url = settings.database.rag_url
    secrets_url = settings.database.secrets_url
    realtime_url = settings.database.realtime_url
    office_url = settings.database.office_url
    worktracker_url = settings.database.worktracker_url
    wiki_url = settings.database.wiki_url
    search_url = settings.database.search_url
    crm_url = settings.database.crm_url
    sync_url = settings.database.sync_url
    stock_url = settings.database.stock_url
    shop_url = settings.database.shop_url
    named_urls = {
        "flows": flows_url,
        "tracing": tracing_url,
        "rag": rag_url,
        "secrets": secrets_url,
        "realtime": realtime_url,
        "office": office_url,
        "worktracker": worktracker_url,
        "wiki": wiki_url,
        "search": search_url,
        "crm": crm_url,
        "sync": sync_url,
        "stock": stock_url,
        "shop": shop_url,
    }
    configured_urls: dict[str, str] = {"shared": shared_url}
    for alias, alias_url in named_urls.items():
        if alias_url is None or alias_url == "":
            continue
        configured_urls[alias] = alias_url
        if all_aliases or alias == "tracing" or alias_url == service_url or alias_url == shared_url:
            databases[alias] = alias_url
    configure_oxyde_aliases(
        configured_urls,
        max_connections=settings.database.pool_max_connections,
        acquire_timeout=settings.database.pool_acquire_timeout_seconds,
    )
    await db.init(settings=pool, **databases)
    logger.info("oxyde.databases_ready", shared_is_default=service_url == shared_url)


async def close_oxyde_databases() -> None:
    """Закрыть все пулы Oxyde процесса."""
    await db.close()


@asynccontextmanager
async def oxyde_databases(
    *,
    default_url: str | None,
    shared_url: str | None,
    all_aliases: bool = False,
) -> AsyncGenerator[None]:
    """Пулы Oxyde на время владельца: DI процесса или сессии тестов.

    Первый владелец открывает пулы через ``init_oxyde_databases``, последний закрывает.
    Вложенный владелец — второй DI в том же интерпретаторе (тесты поднимают несколько
    сервисов) — делит открытые пулы: свою базу он читает именованным алиасом, который
    открывает первый запрос; ``default`` остаётся базой первого владельца.
    """
    global _holders, _held_shared_url
    if shared_url is None or shared_url == "":
        raise RuntimeError("shared database URL is required")
    if _holders == 0:
        await init_oxyde_databases(default_url=default_url, shared_url=shared_url, all_aliases=all_aliases)
        _held_shared_url = shared_url
    elif shared_url != _held_shared_url:
        raise RuntimeError("Oxyde pools of this process are open for another shared database")
    _holders += 1
    try:
        yield
    finally:
        _holders -= 1
        if _holders == 0:
            _held_shared_url = None
            await close_oxyde_databases()
