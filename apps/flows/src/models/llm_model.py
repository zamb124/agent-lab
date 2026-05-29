"""
Модель LLM для хранения списка доступных моделей от провайдеров.
"""

from pydantic import BaseModel, Field


class LLMModel(BaseModel):
    """Модель LLM от провайдера."""

    model_id: str = Field(..., description="ID модели")
    provider: str = Field(..., description="Провайдер из platform LLM provider registry")
