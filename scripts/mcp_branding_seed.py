"""Seed MCP branding icons из git-бандла в S3 + MCPServerBrandingRepository."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from apps.flows.src.container import FlowContainer, get_container
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.services.mcp_branding_seed import seed_mcp_branding_from_bundle
from core.context import Context, clear_context, set_context
from core.identity.system_bootstrap import ensure_system_admin_membership
from core.logging import get_logger
from core.models.i18n_models import Language
from core.models.identity_models import Company, User

logger = get_logger(__name__)


async def _system_context(container: FlowContainer) -> Context:
    company, user = await ensure_system_admin_membership(
        company_repository=container.company_repository,
        subdomain_repository=container.subdomain_repository,
        user_repository=container.user_repository,
    )
    if user is None:
        raise ValueError("system admin user is required for MCP branding seed")
    if company.company_id != "system":
        raise ValueError(f"expected system company, got {company.company_id}")
    return Context(
        user=User(user_id=user.user_id, name=user.name or user.user_id, groups=user.groups),
        host="system",
        session_id="mcp_branding:cli:seed",
        channel="system",
        language=Language.RU,
        active_company=Company(
            company_id=company.company_id,
            name=company.name,
            subdomain=company.subdomain,
        ),
        user_companies=[],
        trace_id="system:mcp_branding:cli:seed",
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed MCP server branding icons from git bundle")
    _ = parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing branding entries",
    )
    _ = parser.add_argument(
        "--server-id",
        action="append",
        dest="server_ids",
        help="Seed only these server_id slugs (repeatable)",
    )
    _ = parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count targets without uploading or writing branding",
    )
    _ = parser.add_argument(
        "--manifest-path",
        type=Path,
        help="Override manifest.yaml path (default from settings.mcp_branding.bundle_path)",
    )
    args = parser.parse_args()

    container = get_container()
    runtime = as_flow_runtime_container(container)
    system_context = await _system_context(container)
    set_context(system_context)
    try:
        server_ids = frozenset(args.server_ids) if args.server_ids else None
        stats = await seed_mcp_branding_from_bundle(
            runtime,
            force=args.force,
            server_ids=server_ids,
            dry_run=args.dry_run,
            manifest_path=args.manifest_path,
        )
    finally:
        clear_context()

    print(
        "mcp branding seed:",
        f"targets={stats.targets}",
        f"seeded={stats.seeded}",
        f"skipped_existing={stats.skipped_existing}",
    )


if __name__ == "__main__":
    asyncio.run(main())
