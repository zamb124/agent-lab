"""Append-only версия переменной компании."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from oxyde import Field as DbField

from core.models.platform_model import PlatformModel
from core.secrets.models.contracts import mask_platform_variable
from core.secrets.models.value import platform_variable_from_row
from core.types import JsonObject
from core.variables.models import PlatformVariable


def platform_variable_from_version(
    row: SecretVariableVersion,
    *,
    include_secret_values: bool,
) -> PlatformVariable:
    return platform_variable_from_row(
        row,
        include_secret_values=include_secret_values,
        updated_at=row.created_at,
    )

class SecretVariableVersion(PlatformModel):
    """Append-only версия переменной. Таблица ``secret_variable_versions``."""

    __database_alias__: ClassVar[str | None] = "secrets"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "secret_variable_versions"
        unique_together: list[tuple[str, str, str]] = [("company_id", "variable_key", "version")]

    secret_variable_version_id: str = DbField(db_pk=True)
    company_id: str = DbField(db_index=True, max_length=100)
    variable_key: str = DbField(max_length=255)
    version: int = DbField(ge=1)
    created_at: datetime = DbField()
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
    async def list_versions(
        cls,
        company_id: str,
        variable_key: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PlatformVariable]:
        rows = await (
            cls.objects.filter(
                company_id=company_id,
                variable_key=variable_key,
            )
            .order_by("-version")
            .limit(limit)
            .offset(offset)
            .all()
        )
        return [
            mask_platform_variable(
                platform_variable_from_version(row, include_secret_values=False)
            )
            for row in rows
        ]

    @classmethod
    async def count_versions(cls, company_id: str, variable_key: str) -> int:
        return await cls.objects.filter(
            company_id=company_id,
            variable_key=variable_key,
        ).count()
