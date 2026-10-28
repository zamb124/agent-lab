"""Подключение S3 компании. Платформенное S3-хранилище строкой не представлено."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import ClassVar, Self

from oxyde import Field as DbField
from pydantic import SerializerFunctionWrapHandler, model_serializer

from core.models.platform_model import PlatformModel
from core.types import JsonObject, require_serializer_json_object

PLATFORM_STORAGE_ID = "platform"
DEFAULT_ROUTE_KIND = "default"


class ObjectStorageState(StrEnum):
    VERIFYING = "verifying"
    ACTIVE = "active"
    DRAINING = "draining"
    RETIRED = "retired"


class ObjectStorage(PlatformModel):
    """Одно S3-подключение компании. Endpoint и бакет не меняются: другое место — новая строка."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    storage_id: str = DbField(db_pk=True)

    class Meta:
        is_table: bool = True
        table_name: str = "object_storages"

    company_id: str = DbField(db_index=True)
    name: str = DbField()
    provider: str = DbField(default="seaweedfs")
    endpoint_url: str = DbField(db_type="TEXT")
    region_name: str = DbField()
    bucket_name: str = DbField()
    path_style: bool = DbField(default=True)
    access_key_id: str = DbField()
    secret_access_key_encrypted: str = DbField(db_type="TEXT")
    credentials_version: int = DbField(default=1)
    state: str = DbField(default=ObjectStorageState.VERIFYING.value, db_index=True)
    verified_at: datetime | None = DbField(default=None)
    created_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    async def list_by_created_at(cls, company_id: str) -> list[Self]:
        """Все хранилища компании, ORDER BY created_at. Предела нет."""
        return await cls.objects.filter(company_id=company_id).order_by("created_at").all()

    @classmethod
    async def require(cls, storage_id: str) -> Self:
        row = await cls.get(storage_id)
        if row is None:
            raise ValueError(f"object storage not found: {storage_id}")
        return row

    @model_serializer(mode="wrap", when_used="json")
    def _json_without_secret(self, handler: SerializerFunctionWrapHandler) -> JsonObject:
        payload = require_serializer_json_object(handler, self, "ObjectStorage")
        if "secret_access_key_encrypted" in payload:
            del payload["secret_access_key_encrypted"]
        payload["has_secret"] = True
        return payload
