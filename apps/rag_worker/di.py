"""DI процесса rag_worker: индексация и обслуживание vector_documents."""

from typing import Annotated

from core.config import BaseSettings
from core.di import http_di, recipe, task_di
from core.di.platform import PlatformDi
from core.rag.base_provider import BaseRAGProvider
from core.rag.factory import get_rag_provider


@recipe
def rag_provider(settings: BaseSettings) -> BaseRAGProvider:
    """Активный провайдер ``rag.default_provider``. ``BaseRAGProvider`` — ABC, экземпляр даёт фабрика."""
    return get_rag_provider(settings=settings)


class RagWorkerDi(PlatformDi, recipes=(rag_provider,)):
    rag_provider: BaseRAGProvider


Di = Annotated[RagWorkerDi, http_di(RagWorkerDi), task_di(RagWorkerDi)]
