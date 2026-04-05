#!/usr/bin/env python3
"""
Миграция JSON в БД сервиса flows: контракт нод (без type tool|function на графе),
react_role вместо tool_type, инлайн function → code для нод.

Запуск из корня репозитория:

  uv run python -m scripts.migrate_flows_contract

Нужен URL БД flows: database.flows_url или database.shared_url в merged config (service flows).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, Callable, Type

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.flows.config import get_settings
from apps.flows.src.db.models import Flows, FlowsVersions, Nodes, Tools
from apps.flows.src.services.flow_contract_normalize import (
    normalize_flow_config_dict,
    normalize_node_config,
    normalize_tool_library_dict,
)

logger = logging.getLogger("migrate_flows_contract")


def _to_async_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    raise ValueError(f"Неподдерживаемый database URL: {url[:48]}...")


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


async def _migrate_table(
    session: AsyncSession,
    model: Type[Any],
    normalize: Callable[[dict[str, Any]], dict[str, Any]],
    label: str,
) -> int:
    result = await session.execute(select(model.key, model.value))
    changed = 0
    for row in result:
        key = row.key
        value = row.value
        if not isinstance(value, dict):
            continue
        new_val = normalize(value)
        if _stable_json(new_val) != _stable_json(value):
            await session.execute(update(model).where(model.key == key).values(value=new_val))
            changed += 1
    logger.info("%s: обновлено строк: %s", label, changed)
    return changed


async def async_main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    url = settings.database.flows_url or settings.database.shared_url
    if not url:
        logger.error("Задайте database.flows_url или database.shared_url")
        return 1

    engine = create_async_engine(_to_async_url(url), echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        total = 0
        total += await _migrate_table(session, Flows, normalize_flow_config_dict, "flows")
        total += await _migrate_table(
            session, FlowsVersions, normalize_flow_config_dict, "flows_versions"
        )
        total += await _migrate_table(session, Nodes, normalize_node_config, "nodes")
        total += await _migrate_table(session, Tools, normalize_tool_library_dict, "tools")
        await session.commit()

    await engine.dispose()
    logger.info("Готово. Всего изменённых строк (по таблицам): %s", total)
    return 0


def main() -> None:
    sys.exit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
