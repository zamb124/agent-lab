"""Platform namespace OpenFGA backfill from shared namespaces registry."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import cast

from sqlalchemy import text

from core.authz.factory import build_authz_service
from core.config import get_settings
from core.db.database import get_session_factory
from core.logging import get_logger
from core.models.identity_models import NamespaceKind
from core.namespace.authz.tuples import (
    platform_namespace_company_editor_tuple,
    platform_namespace_company_link,
    platform_namespace_company_viewer_tuple,
    platform_namespace_owner_tuple,
)

logger = get_logger(__name__)


async def backfill_platform_namespace_authz(
    *, limit: int | None = None
) -> tuple[int, int]:
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError(
            "openfga.enabled must be true for platform namespace authz backfill"
        )
    if not settings.database.shared_url:
        raise RuntimeError(
            "database.shared_url is required for platform namespace authz backfill"
        )

    authz = build_authz_service()
    session_factory = await get_session_factory(settings.database.shared_url)
    company_written = 0
    owners_written = 0

    async with session_factory() as session:
        namespace_sql = (
            "SELECT value->>'name' AS name, "
            "value->>'company_id' AS company_id, "
            "value->>'kind' AS kind, "
            "value->>'owner_user_id' AS owner_user_id "
            "FROM namespaces "
            "WHERE value->>'company_id' IS NOT NULL "
            "AND value->>'name' IS NOT NULL "
            "ORDER BY key"
        )
        if limit is not None:
            namespace_sql = f"{namespace_sql} LIMIT {int(limit)}"
        rows = list((await session.execute(text(namespace_sql))).mappings().all())

    for row in rows:
        namespace = cast(str, row["name"])
        company_id = cast(str, row["company_id"])
        await authz.write(
            [
                platform_namespace_company_link(company_id, namespace),
                platform_namespace_company_viewer_tuple(company_id, namespace),
                platform_namespace_company_editor_tuple(company_id, namespace),
            ]
        )
        company_written += 1

        kind = cast(str | None, row["kind"])
        owner_user_id = cast(str | None, row["owner_user_id"])
        if kind == NamespaceKind.PERSONAL.value:
            if owner_user_id is None or owner_user_id.strip() == "":
                raise ValueError(
                    f"personal namespace {namespace} missing owner_user_id for backfill"
                )
            await authz.write(
                [
                    platform_namespace_owner_tuple(
                        company_id,
                        namespace,
                        owner_user_id,
                    )
                ]
            )
            owners_written += 1

    logger.info(
        "platform namespace authz backfill company=%s owners=%s",
        company_written,
        owners_written,
    )
    return company_written, owners_written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill platform namespace OpenFGA tuples"
    )
    _ = parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    company, owners = asyncio.run(
        backfill_platform_namespace_authz(limit=cast(int | None, args.limit))
    )
    _ = sys.stdout.write(f"company={company} owners={owners}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
