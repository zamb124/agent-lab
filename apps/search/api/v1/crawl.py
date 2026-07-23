"""Crawl admin REST API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.search.dependencies import ContainerDep
from apps.search_worker.tasks.task_names import (
    CRAWL_IMPORT_SEED_DOMAINS,
    CRAWL_ORCHESTRATOR_TICK,
)
from core.crawl.models import (
    CrawlDomain,
    CrawlDomainCreateRequest,
    CrawlDomainPatchRequest,
    CrawlDomainRunResponse,
    CrawlJob,
    CrawlJobCreateRequest,
    CrawlJobQueuedResponse,
    CrawlProfileCreateRequest,
    CrawlProfilePatchRequest,
    CrawlProfileSummary,
    CrawlProfileWithIndex,
    CrawlUrl,
    CrawlUrlAddRequest,
    CrawlUrlDetail,
    CrawlUrlListItem,
    SeedImportRequest,
    SeedImportResult,
    UpsertStats,
)
from core.pagination import OffsetPage
from core.tasks import enqueue

router = APIRouter(prefix="/crawl", tags=["crawl"])


@router.get("/profiles", response_model=OffsetPage[CrawlProfileWithIndex])
async def list_crawl_profiles(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[CrawlProfileWithIndex]:
    return await container.crawl_service.list_profiles(limit=limit, offset=offset)


@router.post("/profiles", response_model=CrawlProfileWithIndex, status_code=201)
async def create_crawl_profile(
    body: CrawlProfileCreateRequest,
    container: ContainerDep,
) -> CrawlProfileWithIndex:
    try:
        return await container.crawl_service.create_profile(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/profiles/{crawl_profile_id}", response_model=CrawlProfileWithIndex)
async def patch_crawl_profile(
    crawl_profile_id: str,
    body: CrawlProfilePatchRequest,
    container: ContainerDep,
) -> CrawlProfileWithIndex:
    try:
        return await container.crawl_service.patch_profile(crawl_profile_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/jobs", response_model=CrawlJobQueuedResponse, status_code=202)
async def start_crawl_job(body: CrawlJobCreateRequest, container: ContainerDep) -> CrawlJobQueuedResponse:
    _ = container
    _ = await enqueue(CRAWL_ORCHESTRATOR_TICK, body.crawl_profile_id)
    return CrawlJobQueuedResponse(crawl_profile_id=body.crawl_profile_id, status="queued")


@router.get("/profiles/{crawl_profile_id}/summary", response_model=CrawlProfileSummary)
async def get_crawl_profile_summary(
    crawl_profile_id: str,
    container: ContainerDep,
) -> CrawlProfileSummary:
    try:
        return await container.crawl_report_service.get_profile_summary(crawl_profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/jobs", response_model=OffsetPage[CrawlJob])
async def list_crawl_jobs(
    container: ContainerDep,
    crawl_profile_id: Annotated[str, Query(min_length=1)],
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[CrawlJob]:
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
    content_type: Annotated[str | None, Query()] = None,
    primary_topic: Annotated[str | None, Query()] = None,
    enriched_only: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[CrawlUrlListItem]:
    try:
        return await container.crawl_report_service.list_urls(
            crawl_profile_id=crawl_profile_id,
            crawl_status=crawl_status,
            domain=domain,
            content_type=content_type,
            primary_topic=primary_topic,
            enriched_only=enriched_only,
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
    try:
        return await container.crawl_report_service.get_url_detail(crawl_url_id, crawl_profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/jobs/{crawl_job_id}", response_model=CrawlJob)
async def get_crawl_job(crawl_job_id: str, container: ContainerDep) -> CrawlJob:
    try:
        return await container.crawl_service.get_job(crawl_job_id)
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
    return await container.crawl_domain_repository.list_page(
        crawl_profile_id=crawl_profile_id,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.post("/domains/{crawl_domain_id}/run", response_model=CrawlDomainRunResponse, status_code=202)
async def run_crawl_domain(
    crawl_domain_id: str,
    container: ContainerDep,
    crawl_profile_id: Annotated[str, Query(min_length=1)],
) -> CrawlDomainRunResponse:
    try:
        return await container.crawl_service.run_domain(crawl_domain_id, crawl_profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/profiles/{crawl_profile_id}/domains", response_model=CrawlDomain, status_code=201)
async def create_crawl_domain(
    crawl_profile_id: str,
    body: CrawlDomainCreateRequest,
    container: ContainerDep,
) -> CrawlDomain:
    try:
        domain = await container.crawl_service.create_domain(crawl_profile_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _ = await enqueue(CRAWL_ORCHESTRATOR_TICK, crawl_profile_id)
    return domain


@router.patch("/domains/{crawl_domain_id}", response_model=CrawlDomain)
async def patch_crawl_domain(
    crawl_domain_id: str,
    body: CrawlDomainPatchRequest,
    container: ContainerDep,
    crawl_profile_id: Annotated[str, Query(min_length=1)],
) -> CrawlDomain:
    try:
        return await container.crawl_service.patch_domain(crawl_domain_id, crawl_profile_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/domains/{crawl_domain_id}", status_code=204)
async def delete_crawl_domain(
    crawl_domain_id: str,
    container: ContainerDep,
    crawl_profile_id: Annotated[str, Query(min_length=1)],
) -> None:
    try:
        await container.crawl_service.delete_domain(crawl_domain_id, crawl_profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/domains/{crawl_domain_id}/urls", response_model=UpsertStats, status_code=202)
async def add_crawl_domain_urls(
    crawl_domain_id: str,
    body: CrawlUrlAddRequest,
    container: ContainerDep,
    crawl_profile_id: Annotated[str, Query(min_length=1)],
) -> UpsertStats:
    try:
        stats = await container.crawl_service.add_domain_urls(crawl_domain_id, crawl_profile_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _ = await enqueue(CRAWL_ORCHESTRATOR_TICK, crawl_profile_id)
    return stats


@router.post("/urls/{crawl_url_id}/recrawl", response_model=CrawlUrl, status_code=202)
async def recrawl_crawl_url(
    crawl_url_id: str,
    container: ContainerDep,
    crawl_profile_id: Annotated[str, Query(min_length=1)],
) -> CrawlUrl:
    try:
        crawl_url = await container.crawl_service.recrawl_url(crawl_url_id, crawl_profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _ = await enqueue(CRAWL_ORCHESTRATOR_TICK, crawl_profile_id)
    return crawl_url


@router.post("/seed/import", response_model=SeedImportResult)
async def import_crawl_seed(body: SeedImportRequest, container: ContainerDep) -> SeedImportResult:
    if body.seed_source == "tranco":
        _ = await enqueue(
            CRAWL_IMPORT_SEED_DOMAINS,
            body.crawl_profile_id,
            body.seed_source,
            body.tranco_limit,
        )
        return SeedImportResult(imported=0, skipped=0)
    try:
        return await container.crawl_service.import_seed(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/profiles/{crawl_profile_id}/seed/tranco", response_model=SeedImportResult)
async def import_tranco_seed_for_profile(
    crawl_profile_id: str,
    body: SeedImportRequest,
    container: ContainerDep,
) -> SeedImportResult:
    if body.crawl_profile_id != crawl_profile_id:
        raise HTTPException(status_code=400, detail="crawl_profile_id mismatch")
    if body.seed_source != "tranco":
        raise HTTPException(status_code=400, detail="seed_source must be tranco")
    _ = container
    _ = await enqueue(
        CRAWL_IMPORT_SEED_DOMAINS,
        crawl_profile_id,
        "tranco",
        body.tranco_limit,
    )
    return SeedImportResult(imported=0, skipped=0)
