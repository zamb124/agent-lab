"""Актуальная переменная компании."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from oxyde import Field as DbField
from oxyde import atomic
from oxyde.exceptions import IntegrityError

from core.models.platform_model import PlatformModel
from core.secrets.models.contracts import (
    encode_variable_value,
    executor_can_resolve,
    mask_platform_variable,
)
from core.secrets.models.secret_variable_version import SecretVariableVersion
from core.secrets.models.value import platform_variable_from_row
from core.types import JsonObject
from core.utils.time import utcnow
from core.variables.models import PlatformVariable, ResolutionContext, ResolvedVariable

_UPSERT_ATTEMPTS = 5

def secret_variable_id(company_id: str, variable_key: str) -> str:
    return f"{len(company_id)}:{company_id}:{len(variable_key)}:{variable_key}"


def secret_variable_version_id(company_id: str, variable_key: str, version: int) -> str:
    return f"{secret_variable_id(company_id, variable_key)}:{version}"

def platform_variable_from_current(
    row: SecretVariable,
    *,
    include_secret_values: bool,
) -> PlatformVariable:
    return platform_variable_from_row(
        row,
        include_secret_values=include_secret_values,
        updated_at=row.updated_at,
    )

class SecretVariable(PlatformModel):
    """Актуальная переменная компании. Таблица ``secret_variables``."""

    __database_alias__: ClassVar[str | None] = "secrets"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "secret_variables"
        unique_together: list[tuple[str, str]] = [("company_id", "variable_key")]

    secret_variable_id: str = DbField(db_pk=True)
    company_id: str = DbField(db_index=True, max_length=100)
    variable_key: str = DbField(max_length=255)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    version: int = DbField(default=1, ge=1)
    secret: bool = DbField(default=False)
    shared_for_execution: bool = DbField(default=False)
    public: bool = DbField(default=False)
    description: str = DbField(default="", db_type="TEXT")
    groups: list[str] = DbField(default_factory=list, db_type="JSONB")
    created_by: str | None = DbField(default=None, max_length=100)
    title: str | None = DbField(default=None, max_length=255)
    order_index: int | None = DbField(default=None)
    value_payload: JsonObject | None = DbField(default=None, db_type="JSONB")
    value_encrypted: str | None = DbField(default=None, db_type="TEXT")

    @classmethod
    async def current_for_variable_key(
        cls,
        company_id: str,
        variable_key: str,
        *,
        include_secret_values: bool,
    ) -> PlatformVariable | None:
        secret_id = secret_variable_id(company_id, variable_key)
        if secret_id == "":
            raise ValueError("SecretVariable secret_variable_id is required")
        row = await cls.objects.filter(secret_variable_id=secret_id).get_or_none()
        if row is None:
            return None
        return platform_variable_from_current(row, include_secret_values=include_secret_values)

    @classmethod
    async def list_for_company(
        cls,
        company_id: str,
        *,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[PlatformVariable]:
        rows = await (
            cls.objects.filter(company_id=company_id)
            .order_by("variable_key")
            .limit(limit)
            .offset(offset)
            .all()
        )
        return [
            mask_platform_variable(
                platform_variable_from_current(row, include_secret_values=False)
            )
            for row in rows
        ]

    @classmethod
    async def count(cls, company_id: str) -> int:
        return await cls.objects.filter(company_id=company_id).count()

    @classmethod
    async def delete_by_company_and_variable_key(cls, company_id: str, variable_key: str) -> bool:
        async with atomic(using="secrets"):
            _ = await SecretVariableVersion.objects.filter(
                company_id=company_id,
                variable_key=variable_key,
            ).delete(using="secrets")
            deleted = await cls.objects.filter(
                secret_variable_id=secret_variable_id(company_id, variable_key),
            ).delete(using="secrets")
        return deleted > 0

    @classmethod
    async def resolve_bundle(cls, context: ResolutionContext) -> list[ResolvedVariable]:
        rows = await cls.objects.filter(company_id=context.company_id).all()
        bundle: list[ResolvedVariable] = []
        for row in rows:
            variable = platform_variable_from_current(row, include_secret_values=True)
            resolvable = executor_can_resolve(variable, context.user_id)
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

    @classmethod
    async def append_version(cls, variable: PlatformVariable) -> PlatformVariable:
        error: IntegrityError | None = None
        for _attempt in range(_UPSERT_ATTEMPTS):
            try:
                return await cls._write_version(variable)
            except IntegrityError as exc:
                error = exc
        if error is None:
            raise RuntimeError("secret variable version write failed without IntegrityError")
        raise error

    @classmethod
    async def _write_version(cls, variable: PlatformVariable) -> PlatformVariable:
        value_payload, value_encrypted = encode_variable_value(variable)
        now = utcnow()
        async with atomic(using="secrets"):
            existing = await (
                cls.objects.filter(
                    company_id=variable.company_id,
                    variable_key=variable.variable_key,
                )
                .for_update()
                .first()
            )
            next_version = 1 if existing is None else existing.version + 1
            if existing is None:
                current = cls(
                    secret_variable_id=secret_variable_id(variable.company_id, variable.variable_key),
                    company_id=variable.company_id,
                    variable_key=variable.variable_key,
                    created_at=now,
                    updated_at=now,
                    version=next_version,
                    secret=variable.secret,
                    shared_for_execution=variable.shared_for_execution,
                    public=variable.public,
                    created_by=variable.created_by,
                    title=variable.title,
                    description=variable.description,
                    order_index=variable.order,
                    groups=list(variable.groups),
                    value_payload=value_payload,
                    value_encrypted=value_encrypted,
                )
                stored = await cls.objects.create(instance=current)
            else:
                existing.version = next_version
                existing.secret = variable.secret
                existing.shared_for_execution = variable.shared_for_execution
                existing.public = variable.public
                existing.created_by = variable.created_by
                existing.title = variable.title
                existing.description = variable.description
                existing.order_index = variable.order
                existing.groups = list(variable.groups)
                existing.value_payload = value_payload
                existing.value_encrypted = value_encrypted
                existing.updated_at = now
                _ = await existing.save()
                stored = existing
            _ = await SecretVariableVersion.objects.create(
                instance=SecretVariableVersion(
                    secret_variable_version_id=secret_variable_version_id(
                        variable.company_id,
                        variable.variable_key,
                        next_version,
                    ),
                    company_id=variable.company_id,
                    variable_key=variable.variable_key,
                    version=next_version,
                    created_at=now,
                    secret=variable.secret,
                    shared_for_execution=variable.shared_for_execution,
                    public=variable.public,
                    created_by=variable.created_by,
                    title=variable.title,
                    description=variable.description,
                    order_index=variable.order,
                    groups=list(variable.groups),
                    value_payload=value_payload,
                    value_encrypted=value_encrypted,
                )
            )
        return platform_variable_from_current(stored, include_secret_values=True)
