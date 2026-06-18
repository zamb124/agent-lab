"""Admin crawl report API (system company, read from platform_search DB)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.frontend.config import get_frontend_settings
from apps.frontend.dependencies import ContainerDep
from core.context import get_context
from core.crawl.models import (
    CrawlDomain,
    CrawlDomainRunResponse,
    CrawlJob,
    CrawlJobCreateRequest,
    CrawlJobQueuedResponse,
    CrawlProfileSummary,
    CrawlProfileWithIndex,
    CrawlUrlDetail,
    CrawlUrlListItem,
)
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.pagination import OffsetPage

router = APIRouter(prefix="/api/crawl-report", tags=["crawl-report"])


def _require_system() -> None:
    context = get_context()
    if context is None:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    company = context.active_company
    if company is None or company.company_id != SYSTEM_COMPANY_ID:
        raise HTTPException(status_code=403, detail="Доступно только для компании system")


def _require_search_db() -> None:
    settings = get_frontend_settings()
    if not settings.database.search_url:
        raise HTTPException(
            status_code=503,
            detail="Crawl report недоступен: не настроен DATABASE__SEARCH_URL.",
        )


@router.get("/profiles", response_model=OffsetPage[CrawlProfileWithIndex])
async def list_crawl_profiles(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[CrawlProfileWithIndex]:
    _require_system()
    _require_search_db()
    return await container.crawl_report_service.list_profiles(limit=limit, offset=offset)


@router.get("/profiles/{crawl_profile_id}/summary", response_model=CrawlProfileSummary)
async def get_crawl_profile_summary(
    crawl_profile_id: str,
    container: ContainerDep,
) -> CrawlProfileSummary:
    _require_system()
    _require_search_db()
    try:
        return await container.crawl_report_service.get_profile_summary(crawl_profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/domains", response_model=OffsetPage[CrawlDomain])
async def list_crawl_domains(
    container: ContainerDep,
    crawl_profile_id: Annotated[str, Query(min_length=1)],
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[CrawlDomain]:
    _require_system()
    _require_search_db()
    try:
        return await container.crawl_report_service.list_domains(
            crawl_profile_id=crawl_profile_id,
            status=status,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/jobs", response_model=OffsetPage[CrawlJob])
async def list_crawl_jobs(
    container: ContainerDep,
    crawl_profile_id: Annotated[str, Query(min_length=1)],
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    _require_system()
    _require_search_db()
    try:
        return await container.crawl_report_service.list_jobs(
            crawl_profile_id=crawl_profile_id,
            status=status,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/urls", response_model=OffsetPage[CrawlUrlListItem])
async def list_crawl_urls(
    container: ContainerDep,
    crawl_profile_id: Annotated[str, Query(min_length=1)],
    crawl_status: Annotated[str | None, Query()] = None,
    domain: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[CrawlUrlListItem]:
    _require_system()
    _require_search_db()
    try:
        return await container.crawl_report_service.list_urls(
            crawl_profile_id=crawl_profile_id,
            crawl_status=crawl_status,
            domain=domain,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/urls/{crawl_url_id}", response_model=CrawlUrlDetail)
async def get_crawl_url_detail(
    crawl_url_id: str,
    container: ContainerDep,
    crawl_profile_id: Annotated[str, Query(min_length=1)],
) -> CrawlUrlDetail:
    _require_system()
    _require_search_db()
    try:
        return await container.crawl_report_service.get_url_detail(crawl_url_id, crawl_profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/jobs", response_model=CrawlJobQueuedResponse, status_code=202)
async def queue_crawl_job(body: CrawlJobCreateRequest, container: ContainerDep) -> CrawlJobQueuedResponse:
    _require_system()
    _require_search_db()
    return await container.search_client.queue_crawl_job(body)


@router.post("/domains/{crawl_domain_id}/run", response_model=CrawlDomainRunResponse, status_code=202)
async def run_crawl_domain(
    crawl_domain_id: str,
    container: ContainerDep,
    crawl_profile_id: Annotated[str, Query(min_length=1)],
) -> CrawlDomainRunResponse:
    _require_system()
    _require_search_db()
    try:
        return await container.search_client.run_crawl_domain(crawl_domain_id, crawl_profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
