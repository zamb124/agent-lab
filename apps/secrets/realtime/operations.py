"""Команды Secrets: версионируемые переменные и секреты компании (один `op_*` на verb)."""

from __future__ import annotations

from pydantic import Field

from apps.secrets.container import SecretsContainer
from core.errors.boundary import PlatformNotFoundError
from core.models import StrictBaseModel
from core.models.identity_models import User
from core.pagination import OffsetPage
from core.request_scope import require_company_admin, require_company_viewer
from core.secrets.models import (
    VariableResolveRequest,
    VariableResolveResponse,
    VariableWriteRequest,
)
from core.variables.models import PlatformVariable, ResolutionContext


class SecretsVariablesListPayload(StrictBaseModel):
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class SecretsVariableKeyPayload(StrictBaseModel):
    variable_key: str = Field(min_length=1)


class SecretsVariableVersionsPayload(SecretsVariableKeyPayload):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class SecretsVariableDeletedResponse(StrictBaseModel):
    status: str = "deleted"
    variable_key: str


async def op_variables_list(
    payload: SecretsVariablesListPayload,
    *,
    user: User,
    container: SecretsContainer,
) -> OffsetPage[PlatformVariable]:
    _ = user
    scope = await require_company_viewer(container.authz_service)
    items = await container.secrets_service.list(
        scope.company_id, limit=payload.limit, offset=payload.offset
    )
    total = await container.secrets_service.count(scope.company_id)
    return OffsetPage[PlatformVariable](
        items=items, total=total, limit=payload.limit, offset=payload.offset
    )


async def op_variables_item(
    payload: SecretsVariableKeyPayload,
    *,
    user: User,
    container: SecretsContainer,
) -> PlatformVariable:
    _ = user
    scope = await require_company_viewer(container.authz_service)
    variable = await container.secrets_service.get(scope.company_id, payload.variable_key)
    if variable is None:
        raise PlatformNotFoundError("Variable not found", error_code="variable_not_found")
    return variable


async def op_variables_create(
    payload: VariableWriteRequest,
    *,
    user: User,
    container: SecretsContainer,
) -> PlatformVariable:
    """Upsert: новая версия существующего ключа или первая версия нового."""
    scope = await require_company_admin(container.authz_service)
    return await container.secrets_service.upsert(
        company_id=scope.company_id, request=payload, created_by=user.user_id
    )


async def op_variables_remove(
    payload: SecretsVariableKeyPayload,
    *,
    user: User,
    container: SecretsContainer,
) -> SecretsVariableDeletedResponse:
    _ = user
    scope = await require_company_admin(container.authz_service)
    deleted = await container.secrets_service.delete(scope.company_id, payload.variable_key)
    if not deleted:
        raise PlatformNotFoundError("Variable not found", error_code="variable_not_found")
    return SecretsVariableDeletedResponse(variable_key=payload.variable_key)


async def op_variables_versions(
    payload: SecretsVariableVersionsPayload,
    *,
    user: User,
    container: SecretsContainer,
) -> OffsetPage[PlatformVariable]:
    _ = user
    scope = await require_company_viewer(container.authz_service)
    current = await container.secrets_service.get(scope.company_id, payload.variable_key)
    if current is None:
        raise PlatformNotFoundError("Variable not found", error_code="variable_not_found")
    items = await container.secrets_service.list_versions(
        scope.company_id, payload.variable_key, limit=payload.limit, offset=payload.offset
    )
    total = await container.secrets_service.count_versions(scope.company_id, payload.variable_key)
    return OffsetPage[PlatformVariable](
        items=items, total=total, limit=payload.limit, offset=payload.offset
    )


async def op_variables_resolve(
    payload: VariableResolveRequest,
    *,
    user: User,
    container: SecretsContainer,
) -> VariableResolveResponse:
    """Эффективный набор переменных для контекста исполнителя (scope overrides)."""
    _ = user
    scope = await require_company_viewer(container.authz_service)
    context = ResolutionContext(
        company_id=scope.company_id,
        user_id=payload.user_id,
        namespace=payload.namespace,
        channel=payload.channel,
    )
    items = await container.secrets_service.resolve_bundle(context)
    return VariableResolveResponse(items=items)
