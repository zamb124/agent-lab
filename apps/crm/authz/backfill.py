"""Backfill CRM OpenFGA tuples from live crm_entities (grants dual-written at runtime)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import cast

from sqlalchemy import text

from apps.crm.authz.tuples import (
    crm_entity_namespace_link,
    crm_entity_owner_tuple,
    crm_namespace_company_editor_tuple,
    crm_namespace_company_link,
    crm_namespace_company_viewer_tuple,
)
from apps.crm.container import get_crm_container
from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)

_ENTITIES_SQL = (
    "SELECT entity_id, company_id, namespace, user_id "
    "FROM crm_entities "
    "ORDER BY created_at ASC"
)


async def _backfill_entities(*, limit: int | None) -> int:
    container = get_crm_container()
    authz = container.authz_service
    if not authz.enabled:
        raise RuntimeError("openfga.enabled must be true for CRM authz backfill")

    written = 0
    async with container.crm_db.session() as session:
        result = await session.execute(text(_ENTITIES_SQL))
        rows = result.fetchall()

    for row in rows:
        if limit is not None and written >= limit:
            break
        entity_id = cast(str, row[0])
        company_id = cast(str, row[1])
        namespace = cast(str, row[2])
        user_id = cast(str | None, row[3])
        if not user_id:
            raise ValueError(f"backfill entity missing user_id: {entity_id}")
        await authz.write(
            [
                crm_namespace_company_link(company_id, namespace),
                crm_namespace_company_viewer_tuple(company_id, namespace),
                crm_namespace_company_editor_tuple(company_id, namespace),
                crm_entity_owner_tuple(entity_id, user_id),
                crm_entity_namespace_link(entity_id, company_id, namespace),
            ]
        )
        written += 1
    logger.info("crm entity backfill complete entities=%s", written)
    return written


async def backfill_crm_authz(*, limit: int | None = None) -> int:
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for CRM authz backfill")
    return await _backfill_entities(limit=limit)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill CRM OpenFGA tuples")
    _ = parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    limit = cast(int | None, args.limit)
    entities = asyncio.run(backfill_crm_authz(limit=limit))
    _ = sys.stdout.write(f"entities={entities}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
