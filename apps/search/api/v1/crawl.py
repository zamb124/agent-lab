"""REST-зеркало команд crawl-администрирования (`search/crawl_*`)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from apps.search.di import Di
from apps.search.models import (
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
from apps.search.realtime.operations import (
    CrawlDomainCreatePayload,
    CrawlDomainRefPayload,
    CrawlDomainsListPayload,
    CrawlDomainUpdatePayload,
    CrawlDomainUrlsAddPayload,
    CrawlJobIdPayload,
    CrawlJobsListPayload,
    CrawlProfileIdPayload,
    CrawlProfileTrancoSeedPayload,
    CrawlProfileTrancoSeedRequest,
    CrawlProfileUpdatePayload,
    CrawlUrlRefPayload,
    CrawlUrlsListPayload,
    SearchPagePayload,
    op_crawl_domains_create,
    op_crawl_domains_list,
    op_crawl_domains_remove,
    op_crawl_domains_run,
    op_crawl_domains_update,
    op_crawl_domains_urls_add,
    op_crawl_jobs_get,
    op_crawl_jobs_list,
    op_crawl_jobs_queue,
    op_crawl_profiles_create,
    op_crawl_profiles_list,
    op_crawl_profiles_summary,
    op_crawl_profiles_tranco_seed,
    op_crawl_profiles_update,
    op_crawl_seed_import,
    op_crawl_urls_get,
    op_crawl_urls_list,
    op_crawl_urls_recrawl,
)
from core.context import require_context
from core.pagination import OffsetPage

router = APIRouter(prefix="/crawl", tags=["crawl"])


@router.get("/profiles", response_model=OffsetPage[CrawlProfileWithIndex])
async def list_crawl_profiles(
    di: Di,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[CrawlProfileWithIndex]:
    return await op_crawl_profiles_list(
        SearchPagePayload(limit=limit, offset=offset), user=require_context().user, di=di
    )


@router.post("/profiles", response_model=CrawlProfileWithIndex, status_code=201)
async def create_crawl_profile(body: CrawlProfileCreateRequest, di: Di) -> CrawlProfileWithIndex:
    return await op_crawl_profiles_create(body, user=require_context().user, di=di)


@router.patch("/profiles/{crawl_profile_id}", response_model=CrawlProfileWithIndex)
async def patch_crawl_profile(
    crawl_profile_id: str, body: CrawlProfilePatchRequest, di: Di
) -> CrawlProfileWithIndex:
    return await op_crawl_profiles_update(
        CrawlProfileUpdatePayload.model_validate(
            {**body.model_dump(exclude_unset=True), "crawl_profile_id": crawl_profile_id}
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/jobs", response_model=CrawlJobQueuedResponse, status_code=202)
async def start_crawl_job(body: CrawlJobCreateRequest, di: Di) -> CrawlJobQueuedResponse:
    return await op_crawl_jobs_queue(body, user=require_context().user, di=di)


@router.get("/profiles/{crawl_profile_id}/summary", response_model=CrawlProfileSummary)
async def get_crawl_profile_summary(crawl_profile_id: str, di: Di) -> CrawlProfileSummary:
    return await op_crawl_profiles_summary(
        CrawlProfileIdPayload(crawl_profile_id=crawl_profile_id), user=require_context().user, di=di
    )


@router.get("/jobs", response_model=OffsetPage[CrawlJob])
async def list_crawl_jobs(
    di: Di,
    crawl_profile_id: Annotated[str, Query(min_length=1)],
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[CrawlJob]:
    return await op_crawl_jobs_list(
        CrawlJobsListPayload(crawl_profile_id=crawl_profile_id, status=status, limit=limit, offset=offset),
        user=require_context().user,
        di=di,
    )


@router.get("/urls", response_model=OffsetPage[CrawlUrlListItem])
async def list_crawl_urls(
    di: Di,
    crawl_profile_id: Annotated[str, Query(min_length=1)],
    crawl_status: Annotated[str | None, Query()] = None,
    domain: Annotated[str | None, Query()] = None,
    content_type: Annotated[str | None, Query()] = None,
    primary_topic: Annotated[str | None, Query()] = None,
    enriched_only: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[CrawlUrlListItem]:
    return await op_crawl_urls_list(
        CrawlUrlsListPayload(
            crawl_profile_id=crawl_profile_id,
            crawl_status=crawl_status,
            domain=domain,
            content_type=content_type,
            primary_topic=primary_topic,
            enriched_only=enriched_only,
            limit=limit,
            offset=offset,
        ),
        user=require_context().user,
        di=di,
    )


@router.get("/urls/{crawl_url_id}", response_model=CrawlUrlDetail)
async def get_crawl_url_detail(
    crawl_url_id: str, di: Di, crawl_profile_id: Annotated[str, Query(min_length=1)]
) -> CrawlUrlDetail:
    return await op_crawl_urls_get(
        CrawlUrlRefPayload(crawl_url_id=crawl_url_id, crawl_profile_id=crawl_profile_id),
        user=require_context().user,
        di=di,
    )


@router.get("/jobs/{crawl_job_id}", response_model=CrawlJob)
async def get_crawl_job(crawl_job_id: str, di: Di) -> CrawlJob:
    return await op_crawl_jobs_get(
        CrawlJobIdPayload(crawl_job_id=crawl_job_id), user=require_context().user, di=di
    )


@router.get("/domains", response_model=OffsetPage[CrawlDomain])
async def list_crawl_domains(
    di: Di,
    crawl_profile_id: Annotated[str, Query(min_length=1)],
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[CrawlDomain]:
    return await op_crawl_domains_list(
        CrawlDomainsListPayload(crawl_profile_id=crawl_profile_id, status=status, limit=limit, offset=offset),
        user=require_context().user,
        di=di,
    )


@router.post("/domains/{crawl_domain_id}/run", response_model=CrawlDomainRunResponse, status_code=202)
async def run_crawl_domain(
    crawl_domain_id: str, di: Di, crawl_profile_id: Annotated[str, Query(min_length=1)]
) -> CrawlDomainRunResponse:
    return await op_crawl_domains_run(
        CrawlDomainRefPayload(crawl_domain_id=crawl_domain_id, crawl_profile_id=crawl_profile_id),
        user=require_context().user,
        di=di,
    )


@router.post("/profiles/{crawl_profile_id}/domains", response_model=CrawlDomain, status_code=201)
async def create_crawl_domain(
    crawl_profile_id: str, body: CrawlDomainCreateRequest, di: Di
) -> CrawlDomain:
    return await op_crawl_domains_create(
        CrawlDomainCreatePayload.model_validate({**body.model_dump(), "crawl_profile_id": crawl_profile_id}),
        user=require_context().user,
        di=di,
    )


@router.patch("/domains/{crawl_domain_id}", response_model=CrawlDomain)
async def patch_crawl_domain(
    crawl_domain_id: str,
    body: CrawlDomainPatchRequest,
    di: Di,
    crawl_profile_id: Annotated[str, Query(min_length=1)],
) -> CrawlDomain:
    return await op_crawl_domains_update(
        CrawlDomainUpdatePayload.model_validate(
            {
                **body.model_dump(exclude_unset=True),
                "crawl_domain_id": crawl_domain_id,
                "crawl_profile_id": crawl_profile_id,
            }
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/domains/{crawl_domain_id}", status_code=204)
async def delete_crawl_domain(
    crawl_domain_id: str, di: Di, crawl_profile_id: Annotated[str, Query(min_length=1)]
) -> None:
    await op_crawl_domains_remove(
        CrawlDomainRefPayload(crawl_domain_id=crawl_domain_id, crawl_profile_id=crawl_profile_id),
        user=require_context().user,
        di=di,
    )


@router.post("/domains/{crawl_domain_id}/urls", response_model=UpsertStats, status_code=202)
async def add_crawl_domain_urls(
    crawl_domain_id: str,
    body: CrawlUrlAddRequest,
    di: Di,
    crawl_profile_id: Annotated[str, Query(min_length=1)],
) -> UpsertStats:
    return await op_crawl_domains_urls_add(
        CrawlDomainUrlsAddPayload(urls=body.urls, crawl_domain_id=crawl_domain_id, crawl_profile_id=crawl_profile_id),
        user=require_context().user,
        di=di,
    )


@router.post("/urls/{crawl_url_id}/recrawl", response_model=CrawlUrl, status_code=202)
async def recrawl_crawl_url(
    crawl_url_id: str, di: Di, crawl_profile_id: Annotated[str, Query(min_length=1)]
) -> CrawlUrl:
    return await op_crawl_urls_recrawl(
        CrawlUrlRefPayload(crawl_url_id=crawl_url_id, crawl_profile_id=crawl_profile_id),
        user=require_context().user,
        di=di,
    )


@router.post("/seed/import", response_model=SeedImportResult)
async def import_crawl_seed(body: SeedImportRequest, di: Di) -> SeedImportResult:
    return await op_crawl_seed_import(body, user=require_context().user, di=di)


@router.post("/profiles/{crawl_profile_id}/seed/tranco", response_model=SeedImportResult)
async def import_tranco_seed_for_profile(
    crawl_profile_id: str, body: CrawlProfileTrancoSeedRequest, di: Di
) -> SeedImportResult:
    return await op_crawl_profiles_tranco_seed(
        CrawlProfileTrancoSeedPayload(crawl_profile_id=crawl_profile_id, tranco_limit=body.tranco_limit),
        user=require_context().user,
        di=di,
    )
