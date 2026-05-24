"""Общие модели речевых провайдеров."""

from pydantic import Field

from core.models.base import StrictBaseModel


class VADSegment(StrictBaseModel):
    """Один сегмент с речью (в секундах относительно начала аудио)."""

    start: float = Field(ge=0.0, description="Начало сегмента (с).")
    end: float = Field(gt=0.0, description="Конец сегмента (с).")
