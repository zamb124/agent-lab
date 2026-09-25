"""DI процесса rag: документы и семантический поиск."""

from typing import Annotated

from core.clients.redis_client import RedisClient
from core.di import http_di, recipe, task_di
from core.di.platform import PlatformDi
from core.rag.post_retrieval_rerank import RerankScoreCache


@recipe
def rerank_score_cache(redis_client: RedisClient) -> RerankScoreCache:
    """Redis-кэш rerank-скорингов. ``RedisTextCache`` — Protocol, конкретный клиент — ``RedisClient``."""
    return RerankScoreCache(redis_client)


class RagDi(PlatformDi, recipes=(rerank_score_cache,)):
    rerank_score_cache: RerankScoreCache


Di = Annotated[RagDi, http_di(RagDi), task_di(RagDi)]
