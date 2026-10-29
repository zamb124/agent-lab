"""DI процесса rag: документы и семантический поиск."""

from typing import Annotated

from core.clients.redis_client import RedisClient
from core.config import BaseSettings
from core.di import http_di, recipe, task_di
from core.di.platform import PlatformDi
from core.rag.base_provider import BaseRAGProvider
from core.rag.factory import get_rag_provider
from core.rag.post_retrieval_rerank import RerankScoreCache


@recipe
def rag_provider(settings: BaseSettings) -> BaseRAGProvider:
    """Активный провайдер ``rag.default_provider``. ``BaseRAGProvider`` — ABC, экземпляр даёт фабрика."""
    return get_rag_provider(settings=settings)


@recipe
def rerank_score_cache(redis_client: RedisClient) -> RerankScoreCache:
    """Redis-кэш rerank-скорингов. ``RedisTextCache`` — Protocol, конкретный клиент — ``RedisClient``."""
    return RerankScoreCache(redis_client)


class RagDi(PlatformDi, recipes=(rag_provider, rerank_score_cache)):
    rag_provider: BaseRAGProvider
    rerank_score_cache: RerankScoreCache


Di = Annotated[RagDi, http_di(RagDi), task_di(RagDi)]
