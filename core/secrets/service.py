"""
Бизнес-логика микросервиса secrets: CRUD переменных + резолв-набор с access policy.

Access policy резолва:
- несекретная переменная — доступна любому исполнителю компании;
- секрет с `shared_for_execution=True` — доступен любому исполнителю компании;
- секрет без `shared_for_execution` — доступен только владельцу (`created_by`); иначе
  значение не раскрывается (`resolvable=False`, payload=None).
"""

from __future__ import annotations

from core.logging import get_logger
from core.secrets.models import VariableWriteRequest
from core.secrets.repository import SecretsRepository
from core.variables.models import (
    PlatformVariable,
    ResolutionContext,
    ResolvedVariable,
    VariableValuePayload,
)

logger = get_logger(__name__)


def _executor_can_resolve(variable: PlatformVariable, executor_user_id: str | None) -> bool:
    if not variable.secret:
        return True
    if variable.shared_for_execution:
        return True
    return executor_user_id is not None and executor_user_id == variable.created_by


class SecretsService:
    """Управление версионируемыми переменными компании и их резолв-набором."""

    def __init__(self, repository: SecretsRepository) -> None:
        self._repository: SecretsRepository = repository

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
        existing = await self._repository.get(
            company_id, request.variable_key, include_secret_values=False
        )
        if existing is not None and existing.created_by is not None:
            variable = variable.model_copy(update={"created_by": existing.created_by})
        stored = await self._repository.upsert(variable)
        logger.info(
            "secrets.variable_upserted",
            variable_key=stored.variable_key,
            version=stored.version,
            secret=stored.secret,
        )
        return self._mask(stored)

    async def get(self, company_id: str, variable_key: str) -> PlatformVariable | None:
        variable = await self._repository.get(
            company_id, variable_key, include_secret_values=False
        )
        return self._mask(variable) if variable is not None else None

    async def list(
        self, company_id: str, *, limit: int = 1000, offset: int = 0
    ) -> list[PlatformVariable]:
        variables = await self._repository.list(
            company_id, include_secret_values=False, limit=limit, offset=offset
        )
        return [self._mask(variable) for variable in variables]

    async def count(self, company_id: str) -> int:
        return await self._repository.count(company_id)

    async def delete(self, company_id: str, variable_key: str) -> bool:
        return await self._repository.delete(company_id, variable_key)

    async def list_versions(
        self,
        company_id: str,
        variable_key: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PlatformVariable]:
        variables = await self._repository.list_versions(
            company_id,
            variable_key,
            include_secret_values=False,
            limit=limit,
            offset=offset,
        )
        return [self._mask(variable) for variable in variables]

    async def count_versions(self, company_id: str, variable_key: str) -> int:
        return await self._repository.count_versions(company_id, variable_key)

    async def resolve_bundle(self, context: ResolutionContext) -> list[ResolvedVariable]:
        variables = await self._repository.list(
            context.company_id, include_secret_values=True
        )
        bundle: list[ResolvedVariable] = []
        for variable in variables:
            resolvable = _executor_can_resolve(variable, context.user_id)
            bundle.append(
                ResolvedVariable(
                    variable_key=variable.variable_key,
                    version=variable.version,
                    secret=variable.secret,
                    shared_for_execution=variable.shared_for_execution,
                    public=variable.public,
                    resolvable=resolvable,
                    payload=variable.payload if resolvable else None,
                )
            )
        return bundle

    @staticmethod
    def _mask(variable: PlatformVariable) -> PlatformVariable:
        """Скрывает payload секрета для CRUD-ответов (значение в API не раскрывается)."""
        if not variable.secret:
            return variable
        return variable.model_copy(update={"payload": VariableValuePayload()})


__all__ = ["SecretsService"]
