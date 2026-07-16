"""Admin crawl report API (system company, read from platform_search DB)."""

from __future__ import annotations

import json
import re
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.frontend.config import get_frontend_settings
from apps.frontend.dependencies import ContainerDep
from core.clients.service_client import ServiceClientError
from core.context import get_context
from core.crawl.models import (
    CrawlDomain,
    CrawlDomainCreateRequest,
    CrawlDomainCreateResponse,
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

_SEARCH_HTTP_STATUS_PREFIX = re.compile(r"^HTTP (\d{3}) при запросе к search: ", re.DOTALL)


def _http_exception_from_search_client(exc: ServiceClientError) -> HTTPException:
    message = str(exc)
    match = _SEARCH_HTTP_STATUS_PREFIX.match(message)
    if match is None:
        return HTTPException(status_code=502, detail="Crawl report: ошибка сервиса search")
    status_code = int(match.group(1))
    body_text = message[match.end() :].strip()
    detail = body_text
    try:
        payload = json.loads(body_text)
        if isinstance(payload, dict):
            detail_raw = payload.get("detail")
            if isinstance(detail_raw, str):
                detail = detail_raw
    except json.JSONDecodeError:
        pass
    if 400 <= status_code < 600:
        return HTTPException(status_code=status_code, detail=detail)
    return HTTPException(status_code=502, detail=detail)


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


@router.post("/domains", response_model=CrawlDomainCreateResponse, status_code=201)
async def create_crawl_domain(
    body: CrawlDomainCreateRequest,
    container: ContainerDep,
) -> CrawlDomainCreateResponse:
    _require_system()
    _require_search_db()
    try:
        return await container.search_client.create_crawl_domain(body)
    except ServiceClientError as exc:
        raise _http_exception_from_search_client(exc) from exc


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
    content_type: Annotated[str | None, Query()] = None,
    primary_topic: Annotated[str | None, Query()] = None,
    enriched_only: Annotated[bool | None, Query()] = None,
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
    except ServiceClientError as exc:
        raise _http_exception_from_search_client(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
