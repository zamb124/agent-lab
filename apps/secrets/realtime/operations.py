"""Команды Secrets: версионируемые переменные и секреты компании (один `op_*` на verb)."""

from __future__ import annotations

from pydantic import Field

from apps.secrets.di import Di
from core.errors.boundary import PlatformNotFoundError
from core.models import StrictBaseModel
from core.models.identity_models import User
from core.pagination import OffsetPage
from core.request_scope import require_company_admin, require_company_viewer
from core.secrets.models import (
    SecretVariable,
    SecretVariableVersion,
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
    di: Di,
) -> OffsetPage[PlatformVariable]:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    items = await SecretVariable.list_masked_by_variable_key_asc(
        scope.company_id, limit=payload.limit, offset=payload.offset
    )
    total = await SecretVariable.count_for_company(scope.company_id)
    return OffsetPage[PlatformVariable](
        items=items, total=total, limit=payload.limit, offset=payload.offset
    )


async def op_variables_item(
    payload: SecretsVariableKeyPayload,
    *,
    user: User,
    di: Di,
) -> PlatformVariable:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    variable = await di.secrets_service.get(scope.company_id, payload.variable_key)
    if variable is None:
        raise PlatformNotFoundError("Variable not found", error_code="variable_not_found")
    return variable


async def op_variables_create(
    payload: VariableWriteRequest,
    *,
    user: User,
    di: Di,
) -> PlatformVariable:
    """Upsert: новая версия существующего ключа или первая версия нового."""
    scope = await require_company_admin(di.authz_service)
    return await di.secrets_service.upsert(
        company_id=scope.company_id, request=payload, created_by=user.user_id
    )


async def op_variables_remove(
    payload: SecretsVariableKeyPayload,
    *,
    user: User,
    di: Di,
) -> SecretsVariableDeletedResponse:
    _ = user
    scope = await require_company_admin(di.authz_service)
    deleted = await SecretVariable.delete_by_company_and_variable_key(
        scope.company_id, payload.variable_key
    )
    if not deleted:
        raise PlatformNotFoundError("Variable not found", error_code="variable_not_found")
    return SecretsVariableDeletedResponse(variable_key=payload.variable_key)


async def op_variables_versions(
    payload: SecretsVariableVersionsPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[PlatformVariable]:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    current = await di.secrets_service.get(scope.company_id, payload.variable_key)
    if current is None:
        raise PlatformNotFoundError("Variable not found", error_code="variable_not_found")
    items = await SecretVariableVersion.list_masked_by_version_desc(
        scope.company_id, payload.variable_key, limit=payload.limit, offset=payload.offset
    )
    total = await SecretVariableVersion.count_versions(scope.company_id, payload.variable_key)
    return OffsetPage[PlatformVariable](
        items=items, total=total, limit=payload.limit, offset=payload.offset
    )


async def op_variables_resolve(
    payload: VariableResolveRequest,
    *,
    user: User,
    di: Di,
) -> VariableResolveResponse:
    """Эффективный набор переменных для контекста исполнителя (scope overrides)."""
    _ = user
    scope = await require_company_viewer(di.authz_service)
    context = ResolutionContext(
        company_id=scope.company_id,
        user_id=payload.user_id,
        namespace=payload.namespace,
        channel=payload.channel,
    )
    items = await SecretVariable.resolve_bundle(context)
    return VariableResolveResponse(items=items)
