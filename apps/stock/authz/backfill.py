"""Stock OpenFGA backfill: company link + membership tuples существующих складов."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import cast

from apps.stock.authz.tuples import (
    stock_warehouse_company_link,
    stock_warehouse_company_member_tuple,
)
from apps.stock.di import StockDi
from apps.stock.models import StockWarehouse
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation
from core.config import get_settings
from core.di import ProcessIdentity, open_di
from core.logging import get_logger

logger = get_logger(__name__)


async def backfill_stock_authz(*, limit: int | None = None) -> int:
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for Stock authz backfill")

    identity = ProcessIdentity(service_name="stock", files_route_segment="stock")
    async with open_di(
        StockDi,
        settings=settings,
        identity=identity,
        database="stock_url",
    ) as di:
        return await _write_warehouse_tuples(di.authz_service, limit=limit)


async def _write_warehouse_tuples(authz: AuthzService, *, limit: int | None) -> int:
    written = 0
    rows = await StockWarehouse.list(limit=limit or 10000)
    for row in rows:
        await authz.write(
            [
                stock_warehouse_company_link(row.warehouse_id, row.company_id),
                stock_warehouse_company_member_tuple(
                    row.warehouse_id, row.company_id, AuthzRelation.VIEWER
                ),
                stock_warehouse_company_member_tuple(
                    row.warehouse_id, row.company_id, AuthzRelation.EDITOR
                ),
            ]
        )
        written += 1
    logger.info("stock.authz.backfill.complete.warehouses", warehouses=written)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill Stock warehouses into OpenFGA")
    _ = parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    limit: int | None = cast(int | None, args.limit)
    warehouses = asyncio.run(backfill_stock_authz(limit=limit))
    _ = sys.stdout.write(f"warehouses={warehouses}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
