"""
Переменные компании: версия и шифрование.

Несекретная переменная доступна любому исполнителю компании.
Секрет с `shared_for_execution` тоже.
Иначе секрет читает только владелец (`created_by`): без доступа `resolvable=False` и payload пуст.
"""

from __future__ import annotations

from core.logging import get_logger
from core.secrets.models import (
    SecretVariable,
    VariableWriteRequest,
    mask_platform_variable,
)
from core.variables.models import PlatformVariable

logger = get_logger(__name__)


class SecretsService:
    """Версионируемые переменные компании и набор для резолва."""

    async def upsert(
        self,
        company_id: str,
        request: VariableWriteRequest,
        created_by: str | None,
    ) -> PlatformVariable:
        variable = PlatformVariable(
            variable_key=request.variable_key,
            company_id=company_id,
            payload=request.payload,
            secret=request.secret,
            shared_for_execution=request.shared_for_execution,
            public=request.public,
            created_by=created_by,
            title=request.title,
            description=request.description,
            order=request.order,
            groups=request.groups,
        )
        existing = await SecretVariable.current_for_variable_key(
            company_id,
            request.variable_key,
            include_secret_values=False,
        )
        if existing is not None and existing.created_by is not None:
            variable = variable.model_copy(update={"created_by": existing.created_by})
        stored = await SecretVariable.append_version(variable)
        logger.info(
            "secrets.variable_upserted",
            variable_key=stored.variable_key,
            version=stored.version,
            secret=stored.secret,
        )
        return mask_platform_variable(stored)

    async def get(self, company_id: str, variable_key: str) -> PlatformVariable | None:
        variable = await SecretVariable.current_for_variable_key(
            company_id,
            variable_key,
            include_secret_values=False,
        )
        return mask_platform_variable(variable) if variable is not None else None


__all__ = ["SecretsService"]
