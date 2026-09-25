"""Локальный crawl MCP registry + provision catalog servers во все компании."""

from __future__ import annotations

import argparse
import asyncio

from apps.flows.config import get_settings
from apps.flows.di import FlowsDi
from apps.flows.src.services.flow_access_service import FlowAccessService
from apps.flows.src.services.mcp_catalog_crawler import (
    crawl_mcp_registry,
    load_mcp_catalog_allowlist,
    upsert_allowlist_seed_entries_only,
)
from apps.flows.src.services.mcp_catalog_provisioner import provision_mcp_catalog_for_company
from core.context import clear_context, set_context
from core.di import ProcessIdentity, open_di
from core.logging import get_logger
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.variables.service import VariablesService

logger = get_logger(__name__)


def _scheduler_company_context(*, company: Company, trace_suffix: str) -> Context:
    return Context(
        user=User(user_id="system", name="System", groups=["admin"]),
        host=company.subdomain if company.subdomain else "system",
        session_id=f"mcp_catalog:{trace_suffix}:{company.company_id}",
        channel="system",
        language=Language.RU,
        active_company=Company(
            company_id=company.company_id,
            name=company.name,
            subdomain=company.subdomain,
        ),
        user_companies=[],
        trace_id=f"system:mcp_catalog:{trace_suffix}:{company.company_id}",
    )


async def _provision_company(
    *,
    company_id: str | None,
    variables_service: VariablesService,
    flow_access_service: FlowAccessService,
) -> None:
    companies = await Company.list(limit=10_000)
    if company_id is not None:
        companies = [company for company in companies if company.company_id == company_id]
        if not companies:
            raise ValueError(f"Company not found: {company_id}")

    totals = {"added": 0, "updated": 0, "sync_ok": 0, "sync_failed": 0}
    for company in companies:
        company_context = _scheduler_company_context(
            company=company,
            trace_suffix="cli:provision",
        )
        set_context(company_context)
        try:
            stats = await provision_mcp_catalog_for_company(
                variables_service=variables_service,
                flow_access_service=flow_access_service,
            )
        finally:
            clear_context()
        totals["added"] += stats.added
        totals["updated"] += stats.updated
        totals["sync_ok"] += stats.sync_ok
        totals["sync_failed"] += stats.sync_failed
        logger.info(
            "MCP catalog provision company=%s added=%s updated=%s sync_ok=%s sync_failed=%s",
            company.company_id,
            stats.added,
            stats.updated,
            stats.sync_ok,
            stats.sync_failed,
        )
    print(f"provision totals: {totals}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl MCP registry and provision catalog servers")
    _ = parser.add_argument(
        "--company-id",
        help="Provision only this company (default: all companies)",
    )
    _ = parser.add_argument(
        "--provision-only",
        action="store_true",
        help="Skip registry crawl, only provision from existing catalog",
    )
    _ = parser.add_argument(
        "--crawl-only",
        action="store_true",
        help="Only crawl registry, skip company provision",
    )
    _ = parser.add_argument(
        "--seeds-only",
        action="store_true",
        help="Only upsert curated allowlist seeds (skip full registry crawl)",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.mcp_catalog.enabled:
        raise RuntimeError("mcp_catalog.enabled is false in settings")

    if not args.provision_only:
        if args.seeds_only:
            allowlist = load_mcp_catalog_allowlist()
            seed_stats = await upsert_allowlist_seed_entries_only(
                allowlist=allowlist,
            )
            print(
                "seeds:",
                f"upserted={seed_stats.upserted}",
                f"verified={seed_stats.verified}",
                f"verify_failed={seed_stats.verify_failed}",
            )
        else:
            crawl_stats = await crawl_mcp_registry()
            print(
                "crawl:",
                f"fetched={crawl_stats.fetched}",
                f"upserted={crawl_stats.upserted}",
                f"verified={crawl_stats.verified}",
                f"verify_failed={crawl_stats.verify_failed}",
                f"deprecated={crawl_stats.deprecated}",
            )

    if args.crawl_only or args.seeds_only:
        return

    if settings.mcp_catalog.auto_provision == "disabled":
        print("auto_provision=disabled; skip company provision (companies install from Store)")
        return

    identity = ProcessIdentity(service_name="flows", files_route_segment="flows")
    async with open_di(
        FlowsDi,
        settings=settings,
        identity=identity,
        database="flows_url",
    ) as di:
        await _provision_company(
            company_id=args.company_id,
            variables_service=di.variables_service,
            flow_access_service=di.flow_access_service,
        )


if __name__ == "__main__":
    asyncio.run(main())
