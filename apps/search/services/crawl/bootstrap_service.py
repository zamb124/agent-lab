"""Idempotent crawl pipeline bootstrap on worker startup."""

from __future__ import annotations

from apps.search.config import SearchCrawlConfig
from apps.search.db.crawl_repositories import CrawlDomainRepository, CrawlProfileRepository
from apps.search_worker.broker import broker as search_worker_broker
from apps.search_worker.tasks.task_names import CRAWL_IMPORT_SEED_DOMAINS_TASK_NAME
from core.crawl.models import CrawlBootstrapResult


async def _kiq_task(task_name: str, *args: object, **kwargs: object) -> None:
    task = search_worker_broker.find_task(task_name)
    if task is None:
        raise RuntimeError(f"task is not registered: {task_name}")
    _ = await task.kiq(*args, **kwargs)


class CrawlBootstrapService:
    def __init__(
        self,
        *,
        crawl_profile_repository: CrawlProfileRepository,
        crawl_domain_repository: CrawlDomainRepository,
        crawl_config: SearchCrawlConfig,
    ) -> None:
        self._crawl_profile_repository: CrawlProfileRepository = crawl_profile_repository
        self._crawl_domain_repository: CrawlDomainRepository = crawl_domain_repository
        self._crawl_config: SearchCrawlConfig = crawl_config

    async def ensure_crawl_pipeline_ready(self) -> CrawlBootstrapResult:
        crawl_profile_id = self._crawl_config.default_crawl_profile_id
        if not self._crawl_config.bootstrap_tranco_on_empty:
            domain_count = await self._crawl_domain_repository.count_for_profile(crawl_profile_id)
            return CrawlBootstrapResult(
                crawl_profile_id=crawl_profile_id,
                action="bootstrap_disabled",
                domain_count=domain_count,
            )

        profile_bundle = await self._crawl_profile_repository.get_with_index(crawl_profile_id)
        if not profile_bundle.profile.enabled:
            raise ValueError(f"crawl profile disabled: {crawl_profile_id}")

        domain_count = await self._crawl_domain_repository.count_for_profile(crawl_profile_id)
        if domain_count > 0:
            return CrawlBootstrapResult(
                crawl_profile_id=crawl_profile_id,
                action="skipped_seed",
                domain_count=domain_count,
            )

        await _kiq_task(
            CRAWL_IMPORT_SEED_DOMAINS_TASK_NAME,
            crawl_profile_id,
            "tranco",
            self._crawl_config.tranco_seed_limit,
        )
        return CrawlBootstrapResult(
            crawl_profile_id=crawl_profile_id,
            action="queued_seed",
            domain_count=0,
        )
