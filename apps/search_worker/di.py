"""DI процесса search_worker: crawl tick, fetch и bootstrap пайплайна."""

from typing import Annotated

from apps.search.components import WORKER_RECIPES
from apps.search.services.crawl.orchestrator_service import CrawlOrchestratorService
from core.di import http_di, task_di
from core.di.platform import PlatformDi


class SearchWorkerDi(PlatformDi, recipes=WORKER_RECIPES):
    crawl_orchestrator_service: CrawlOrchestratorService


Di = Annotated[SearchWorkerDi, http_di(SearchWorkerDi), task_di(SearchWorkerDi)]
