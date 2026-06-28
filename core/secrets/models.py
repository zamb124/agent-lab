"""API-контракты микросервиса secrets (REST-зеркало команд переменных)."""

from __future__ import annotations

from pydantic import Field

from core.models import StrictBaseModel
from core.variables.models import (
    ResolvedVariable,
    VariableValuePayload,
)


class VariableWriteRequest(StrictBaseModel):
    """Создание/обновление переменной. `company_id`/`created_by` берутся из контекста."""

    variable_key: str
    payload: VariableValuePayload = Field(default_factory=VariableValuePayload)
    secret: bool = False
    shared_for_execution: bool = False
    public: bool = False
    title: str | None = None
    description: str = ""
    order: int | None = None
    groups: list[str] = Field(default_factory=list)


class VariableResolveRequest(StrictBaseModel):
    """Контекст исполнителя для резолва (company_id берётся из auth-контекста сервиса)."""

    user_id: str | None = None
    namespace: str | None = None
    channel: str | None = None


class VariableResolveResponse(StrictBaseModel):
    """Набор переменных компании для движка резолвинга на стороне потребителя."""

    items: list[ResolvedVariable] = Field(default_factory=list)


__all__ = [
    "VariableResolveRequest",
    "VariableResolveResponse",
    "VariableWriteRequest",
]
