"""TaskIQ: crawl MCP registry, provision companies, resync catalog tools."""

from __future__ import annotations

from typing import TypedDict

from apps.flows.config import get_settings
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.services.mcp_branding_seed import seed_mcp_branding_from_bundle
from apps.flows.src.services.mcp_catalog_crawler import MCPCatalogCrawlStats, crawl_mcp_registry
from apps.flows.src.services.mcp_catalog_provisioner import (
    provision_mcp_catalog_for_company,
    resync_catalog_tools_for_company,
)
from apps.idle_worker.broker import broker as idle_broker
from apps.idle_worker.container import get_container
from apps.idle_worker.tasks.llm_models_tasks import build_scheduler_auth_context
from core.context import Context, clear_context, set_context
from core.logging import get_logger
from core.models.i18n_models import Language
from core.models.identity_models import Company, User

logger = get_logger(__name__)

MCP_CATALOG_CRAWL_TASK_NAME = "mcp_catalog_crawl_task"
MCP_CATALOG_PROVISION_COMPANIES_TASK_NAME = "mcp_catalog_provision_companies_task"
MCP_CATALOG_RESYNC_TOOLS_TASK_NAME = "mcp_catalog_resync_tools_task"


class MCPCatalogCrawlTaskResult(TypedDict):
    fetched: int
    upserted: int
    deprecated: int
    verified: int
    verify_failed: int
    provision_companies: int


class MCPCatalogProvisionCompaniesTaskResult(TypedDict):
    companies: int
    added: int
    updated: int
    skipped_locked: int
    deprecated: int
    sync_ok: int
    sync_failed: int


class MCPCatalogResyncToolsTaskResult(TypedDict):
    companies: int
    sync_ok: int
    sync_failed: int


async def _company_context(*, company: Company, trace_suffix: str) -> Context:
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


@idle_broker.task(task_name=MCP_CATALOG_CRAWL_TASK_NAME, queue_name="idle")
async def mcp_catalog_crawl_task(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
) -> MCPCatalogCrawlTaskResult:
    _ = company_id
    settings = get_settings()
    if not settings.mcp_catalog.enabled:
        return {
            "fetched": 0,
            "upserted": 0,
            "deprecated": 0,
            "verified": 0,
            "verify_failed": 0,
            "provision_companies": 0,
        }

    container = get_container()
    scheduler_context = await build_scheduler_auth_context(
        container=container,
        trace_id=f"scheduler:{MCP_CATALOG_CRAWL_TASK_NAME}:{schedule_task_id}",
        session_id=f"{MCP_CATALOG_CRAWL_TASK_NAME}:{schedule_task_id}",
    )
    set_context(scheduler_context)
    try:
        runtime = as_flow_runtime_container(container)
        crawl_stats: MCPCatalogCrawlStats | None = None
        try:
            crawl_stats = await crawl_mcp_registry(container=runtime)
            if settings.mcp_branding.seed_after_crawl:
                branding_stats = await seed_mcp_branding_from_bundle(runtime, force=False)
                logger.info(
                    "MCP branding seed after crawl: targets=%s seeded=%s skipped_existing=%s",
                    branding_stats.targets,
                    branding_stats.seeded,
                    branding_stats.skipped_existing,
                )
        except Exception:
            logger.exception("MCP catalog crawl failed; continuing with provision for existing catalog")
        provision_result: MCPCatalogProvisionCompaniesTaskResult = {
            "companies": 0,
            "added": 0,
            "updated": 0,
            "skipped_locked": 0,
            "deprecated": 0,
            "sync_ok": 0,
            "sync_failed": 0,
        }
        if settings.mcp_catalog.auto_provision != "disabled":
            provision_result = await mcp_catalog_provision_companies_task(
                schedule_task_id=schedule_task_id,
            )
        if crawl_stats is None:
            return {
                "fetched": 0,
                "upserted": 0,
                "deprecated": 0,
                "verified": 0,
                "verify_failed": 0,
                "provision_companies": provision_result["companies"],
            }
        return {
            "fetched": crawl_stats.fetched,
            "upserted": crawl_stats.upserted,
            "deprecated": crawl_stats.deprecated,
            "verified": crawl_stats.verified,
            "verify_failed": crawl_stats.verify_failed,
            "provision_companies": provision_result["companies"],
        }
    finally:
        clear_context()


@idle_broker.task(task_name=MCP_CATALOG_PROVISION_COMPANIES_TASK_NAME, queue_name="idle")
async def mcp_catalog_provision_companies_task(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
) -> MCPCatalogProvisionCompaniesTaskResult:
    settings = get_settings()
    if settings.mcp_catalog.auto_provision == "disabled":
        return {
            "companies": 0,
            "added": 0,
            "updated": 0,
            "skipped_locked": 0,
            "deprecated": 0,
            "sync_ok": 0,
            "sync_failed": 0,
        }

    container = get_container()
    runtime = as_flow_runtime_container(container)
    companies = await container.company_repository.list(limit=10_000)
    if company_id is not None:
        companies = [company for company in companies if company.company_id == company_id]
        if not companies:
            raise ValueError(f"Company not found for MCP catalog provision: {company_id}")

    totals = MCPCatalogProvisionCompaniesTaskResult(
        companies=len(companies),
        added=0,
        updated=0,
        skipped_locked=0,
        deprecated=0,
        sync_ok=0,
        sync_failed=0,
    )
    for company in companies:
        company_context = await _company_context(
            company=company,
            trace_suffix=f"provision:{schedule_task_id}",
        )
        set_context(company_context)
        try:
            stats = await provision_mcp_catalog_for_company(container=runtime)
        finally:
            clear_context()
        totals["added"] += stats.added
        totals["updated"] += stats.updated
        totals["skipped_locked"] += stats.skipped_locked
        totals["deprecated"] += stats.deprecated
        totals["sync_ok"] += stats.sync_ok
        totals["sync_failed"] += stats.sync_failed

    logger.info(
        "MCP catalog provision companies done: schedule_task_id=%s %s",
        schedule_task_id,
        totals,
    )
    return totals


@idle_broker.task(task_name=MCP_CATALOG_RESYNC_TOOLS_TASK_NAME, queue_name="idle")
async def mcp_catalog_resync_tools_task(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
) -> MCPCatalogResyncToolsTaskResult:
    settings = get_settings()
    if settings.mcp_catalog.auto_provision == "disabled":
        return {"companies": 0, "sync_ok": 0, "sync_failed": 0}

    container = get_container()
    runtime = as_flow_runtime_container(container)
    companies = await container.company_repository.list(limit=10_000)
    if company_id is not None:
        companies = [company for company in companies if company.company_id == company_id]

    sync_ok_total = 0
    sync_failed_total = 0
    for company in companies:
        company_context = await _company_context(
            company=company,
            trace_suffix=f"resync:{schedule_task_id}",
        )
        set_context(company_context)
        try:
            sync_ok, sync_failed = await resync_catalog_tools_for_company(container=runtime)
        finally:
            clear_context()
        sync_ok_total += sync_ok
        sync_failed_total += sync_failed

    result: MCPCatalogResyncToolsTaskResult = {
        "companies": len(companies),
        "sync_ok": sync_ok_total,
        "sync_failed": sync_failed_total,
    }
    logger.info(
        "MCP catalog resync tools done: schedule_task_id=%s %s",
        schedule_task_id,
        result,
    )
    return result
