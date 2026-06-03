"""Единая запись каталога моделей провайдеров.

Исторически сущность называлась ``LLMModel`` и лежит в существующем storage
каталоге flows. Архитектурно это теперь provider model catalog: одна запись
может описывать LLM, embedding, rerank, image или voice capability.
"""

from typing import Literal

from pydantic import BaseModel, Field

from core.ai.providers import LLM_CAPABILITIES, AICapability
from core.types import JsonObject

ModelMetadataStatus = Literal["discovered", "verified"]


class LLMModel(BaseModel):
    """Модель провайдера с capability metadata из dynamic discovery/probe."""

    model_id: str = Field(..., description="ID модели у провайдера")
    provider: str = Field(..., description="Провайдер из platform provider registry")
    capabilities: tuple[AICapability, ...] = Field(
        default=LLM_CAPABILITIES,
        description="Функциональные роли модели; старые записи без поля считаются LLM.",
    )
    input_modalities: tuple[str, ...] = Field(default_factory=tuple)
    output_modalities: tuple[str, ...] = Field(default_factory=tuple)
    supported_parameters: tuple[str, ...] = Field(default_factory=tuple)
    context_length: int | None = None
    created: int | None = None
    native_dimension: int | None = Field(
        default=None,
        description="Нативная размерность embedding-вектора, если provider/probe её подтвердил.",
    )
    storage_dimension: int | None = Field(
        default=None,
        description="Размерность, совместимая с текущим storage/pgvector, если подтверждена.",
    )
    mrl_output_dimension: int | None = Field(
        default=None,
        description="Размерность усечения/вывода для storage, если модель допускает безопасное снижение.",
    )
    supports_tools: bool = False
    supports_structured_output: bool = False
    is_free: bool | None = None
    free_reason: str | None = None
    metadata_status: ModelMetadataStatus = "discovered"
    raw: JsonObject = Field(default_factory=dict)
