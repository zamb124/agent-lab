"""Чтение значения из строки переменной или её версии."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from core.secrets.crypto import decrypt_secret
from core.types import JsonObject, require_json_object
from core.variables.models import PlatformVariable, VariableValuePayload

_MASKED_PAYLOAD = VariableValuePayload()


class StoredSecretRow(Protocol):
    """Общие поля актуальной переменной и append-only версии."""

    variable_key: str
    company_id: str
    version: int
    secret: bool
    shared_for_execution: bool
    public: bool
    created_by: str | None
    title: str | None
    description: str
    order_index: int | None
    groups: list[str]
    created_at: datetime
    value_payload: JsonObject | None
    value_encrypted: str | None


def variable_value_payload(
    row: StoredSecretRow,
    *,
    include_secret_values: bool,
) -> VariableValuePayload:
    if row.secret:
        if not include_secret_values:
            return _MASKED_PAYLOAD.model_copy(deep=True)
        if row.value_encrypted is None:
            raise ValueError(f"Secret variable '{row.variable_key}' without value_encrypted")
        return VariableValuePayload.model_validate_json(decrypt_secret(row.value_encrypted))
    if row.value_payload is None:
        raise ValueError(f"Variable '{row.variable_key}' without value_payload")
    return VariableValuePayload.model_validate(
        require_json_object(row.value_payload, "value_payload")
    )


def platform_variable_from_row(
    row: StoredSecretRow,
    *,
    include_secret_values: bool,
    updated_at: datetime,
) -> PlatformVariable:
    return PlatformVariable(
        variable_key=row.variable_key,
        company_id=row.company_id,
        version=row.version,
        payload=variable_value_payload(row, include_secret_values=include_secret_values),
        secret=row.secret,
        shared_for_execution=row.shared_for_execution,
        public=row.public,
        created_by=row.created_by,
        title=row.title,
        description=row.description,
        order=row.order_index,
        groups=list(row.groups),
        created_at=row.created_at,
        updated_at=updated_at,
    )
