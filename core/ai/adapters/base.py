from __future__ import annotations

from abc import ABC, abstractmethod

from core.ai.models import AIModelRecord, AIRuntimeEndpoint
from core.ai.providers import AICapability


class AIProviderAdapter(ABC):
    provider: str

    @abstractmethod
    async def list_models(self, *, probe_embeddings: bool = True) -> list[AIModelRecord]:
        raise NotImplementedError

    @abstractmethod
    def is_configured(self) -> bool:
        raise NotImplementedError

    async def probe_model(self, record: AIModelRecord) -> AIModelRecord:
        return record

    async def probe_embedding_dimension(self, model_id: str) -> int | None:
        _ = model_id
        return None

    @abstractmethod
    def runtime_endpoint(self, capability: AICapability) -> AIRuntimeEndpoint:
        raise NotImplementedError
