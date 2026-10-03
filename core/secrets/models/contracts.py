"""Тела команд переменных и маскирование значения."""

from __future__ import annotations

from pydantic import Field

from core.models import StrictBaseModel
from core.secrets.crypto import encrypt_secret
from core.types import JsonObject, require_json_object
from core.variables.models import PlatformVariable, ResolvedVariable, VariableValuePayload


def executor_can_resolve(variable: PlatformVariable, executor_user_id: str | None) -> bool:
    if not variable.secret:
        return True
    if variable.shared_for_execution:
        return True
    return executor_user_id is not None and executor_user_id == variable.created_by

def encode_variable_value(variable: PlatformVariable) -> tuple[JsonObject | None, str | None]:
    if variable.secret:
        return None, encrypt_secret(variable.payload.model_dump_json())
    return require_json_object(variable.payload.model_dump(mode="json"), "payload"), None


def mask_platform_variable(variable: PlatformVariable) -> PlatformVariable:
    if not variable.secret:
        return variable
    return variable.model_copy(update={"payload": VariableValuePayload()})

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
