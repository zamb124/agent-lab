"""Platform namespace OpenFGA backfill from shared namespaces registry."""

from __future__ import annotations

import asyncio
import sys

from core.authz.factory import build_authz_service
from core.config import get_settings
from core.db.oxyde_runtime import close_oxyde_databases, init_oxyde_databases
from core.logging import get_logger
from core.models.identity_models import Namespace, NamespaceKind
from core.namespace.authz.tuples import (
    platform_namespace_company_editor_tuple,
    platform_namespace_company_link,
    platform_namespace_company_viewer_tuple,
    platform_namespace_owner_tuple,
)

logger = get_logger(__name__)


def _parse_limit(argv: list[str] | None) -> int | None:
    tokens = list(sys.argv[1:]) if argv is None else argv
    if len(tokens) == 0:
        return None
    if len(tokens) != 2 or tokens[0] != "--limit":
        raise RuntimeError("usage: python -m core.namespace.authz.backfill [--limit N]")
    token = tokens[1]
    digits = token.lstrip("-")
    if digits == "" or not digits.isdigit():
        raise RuntimeError("--limit must be an integer")
    return int(token)


async def backfill_platform_namespace_authz(
    *, limit: int | None = None
) -> tuple[int, int]:
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError(
            "openfga.enabled must be true for platform namespace authz backfill"
        )
    shared_url = settings.database.shared_url
    if shared_url is None or shared_url == "":
        raise RuntimeError(
            "database.shared_url is required for platform namespace authz backfill"
        )

    authz = build_authz_service()
    company_written = 0
    owners_written = 0

    for row in await Namespace.partial_company_rows_by_namespace_id_asc(limit=limit):
        await authz.write(
            [
                platform_namespace_company_link(row.company_id, row.name),
                platform_namespace_company_viewer_tuple(row.company_id, row.name),
                platform_namespace_company_editor_tuple(row.company_id, row.name),
            ]
        )
        company_written += 1
        if row.kind == NamespaceKind.PERSONAL:
            owner_user_id = row.owner_user_id
            if owner_user_id is None or owner_user_id.strip() == "":
                raise ValueError(
                    f"personal namespace {row.name} missing owner_user_id for backfill"
                )
            await authz.write(
                [
                    platform_namespace_owner_tuple(
                        row.company_id,
                        row.name,
                        owner_user_id,
                    )
                ]
            )
            owners_written += 1

    logger.info(
        "platform.namespace.authz.backfill.company",
        company=company_written,
        owners=owners_written,
    )
    return company_written, owners_written


def main(argv: list[str] | None = None) -> int:
    limit = _parse_limit(argv)

    async def _run() -> tuple[int, int]:
        settings = get_settings()
        shared_url = settings.database.shared_url
        if shared_url is None or shared_url == "":
            raise RuntimeError(
                "database.shared_url is required for platform namespace authz backfill"
            )
        await init_oxyde_databases(default_url=shared_url, shared_url=shared_url)
        try:
            return await backfill_platform_namespace_authz(limit=limit)
        finally:
            await close_oxyde_databases()

    company, owners = asyncio.run(_run())
    _ = sys.stdout.write(f"company={company} owners={owners}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
