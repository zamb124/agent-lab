#!/usr/bin/env python3
"""
Устарело: данные в ``flows`` / ``flows_versions`` мигрируют ревизией Alembic ``agents_0005``.

Скрипт оставлен для ручного прогона на старых окружениях без прохода ``alembic upgrade``;
предпочтительно: ``uv run python scripts/db_migrate.py flows`` (или эквивалент для вашего деплоя).
"""

from __future__ import annotations

import asyncio
import json
import sys

from apps.flows.src.services.flow_contract_normalize import normalize_flow_config_dict

from apps.flows.src.container import get_container
from apps.flows.src.models import FlowConfig


async def _migrate_table(storage: object, table: str) -> tuple[int, int]:
    scanned = 0
    updated = 0
    offset = 0
    batch_size = 500
    while True:
        batch = await storage._get_all_by_prefix_and_table("company:", table, batch_size, offset)
        if not batch:
            break
        for key, raw in batch.items():
            if ":flow:" not in key:
                continue
            scanned += 1
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                print(f"skip non-json key={key}", file=sys.stderr)
                continue
            if "skills" not in payload:
                continue
            normalized = normalize_flow_config_dict(payload)
            cfg = FlowConfig.model_validate(normalized)
            new_raw = cfg.model_dump_json()
            if new_raw != raw:
                await storage._set_with_table(key, new_raw, table)
                updated += 1
                print(f"updated table={table} key={key}")
        if len(batch) < batch_size:
            break
        offset += batch_size
    return scanned, updated


async def main() -> None:
    container = get_container()
    storage = container.storage
    total_updated = 0
    for table in ("flows", "flows_versions"):
        scanned, upd = await _migrate_table(storage, table)
        print(f"{table}: scanned_flow_keys={scanned} rows_updated={upd}")
        total_updated += upd
    print(f"done: total_rows_updated={total_updated}")


if __name__ == "__main__":
    asyncio.run(main())
