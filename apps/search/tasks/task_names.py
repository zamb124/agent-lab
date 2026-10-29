"""Declaration-модуль search задач (очередь ``search``).

Лёгкий: только объявления. Импортируется и producer'ами (для ``enqueue``),
и impl-модулями (для ``@platform_task``).
"""

from core.tasks import declare_task

CRAWL_ORCHESTRATOR_TICK = declare_task(
    "crawl_orchestrator_tick", queue="search", scheduled=True, retry=True, max_retries=1
)
CRAWL_DISCOVER_DOMAIN = declare_task(
    "crawl_discover_domain", queue="search", retry=True, max_retries=2
)
CRAWL_FETCH_URL = declare_task(
    "crawl_fetch_url", queue="search", retry=True, max_retries=3
)
CRAWL_ENRICH_URL = declare_task(
    "crawl_enrich_url", queue="search", retry=True, max_retries=2
)
CRAWL_IMPORT_SEED_DOMAINS = declare_task(
    "crawl_import_seed_domains", queue="search", retry=True, max_retries=2
)
CRAWL_RECLAIM_STALE_FETCHING = declare_task(
    "crawl_reclaim_stale_fetching", queue="search", scheduled=True, retry=True, max_retries=1
)

__all__ = [
    "CRAWL_DISCOVER_DOMAIN",
    "CRAWL_ENRICH_URL",
    "CRAWL_FETCH_URL",
    "CRAWL_IMPORT_SEED_DOMAINS",
    "CRAWL_ORCHESTRATOR_TICK",
    "CRAWL_RECLAIM_STALE_FETCHING",
]
