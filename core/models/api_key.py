"""API-ключ компании. Таблица ``api_keys`` в ``platform_shared``."""

from datetime import datetime, timezone
from typing import ClassVar, Self, override

from oxyde import Field as DbField
from pydantic import SerializerFunctionWrapHandler, model_serializer

from core.context import require_active_company
from core.models.platform_model import PlatformModel
from core.types import JsonObject, require_serializer_json_object


class ApiKeyRecord(PlatformModel):
    """Ключ компании. ``key_hash`` хранится в таблице и не попадает в JSON."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    key_id: str = DbField(db_pk=True)

    class Meta:
        is_table: bool = True
        table_name: str = "api_keys"

    company_id: str = DbField(db_index=True)
    name: str = DbField()
    key_hash: str = DbField(db_unique=True)
    key_prefix: str = DbField()
    scopes: list[str] = DbField(default_factory=list, db_type="JSONB")
    created_by: str = DbField(db_index=True)
    revoked: bool = DbField(default=False, db_index=True)
    created_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc), db_index=True)
    last_used: datetime | None = DbField(default=None)

    @model_serializer(mode="wrap", when_used="json")
    def _json_without_key_hash(self, handler: SerializerFunctionWrapHandler) -> JsonObject:
        payload = require_serializer_json_object(handler, self, "ApiKeyRecord")
        if "key_hash" in payload:
            del payload["key_hash"]
        return payload

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = update_fields
        if is_create and "created_at" not in self.model_fields_set:
            self.created_at = datetime.now(timezone.utc)

    @classmethod
    def _require_company(cls, company_id: str) -> str:
        active_company_id = require_active_company().company_id
        if company_id != active_company_id:
            raise ValueError("company_id does not match the active company")
        return company_id

    @classmethod
    async def list_by_company(
        cls,
        company_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Self]:
        scoped_company_id = cls._require_company(company_id)
        return await (
            cls.objects.filter(company_id=scoped_company_id, revoked=False)
            .order_by("-created_at")
            .limit(limit)
            .offset(offset)
            .all()
        )

    @classmethod
    async def active_by_hash(cls, key_hash: str) -> Self | None:
        return await cls.objects.filter(key_hash=key_hash, revoked=False).get_or_none()

    @classmethod
    async def touch_last_used(cls, key_id: str, company_id: str) -> None:
        affected = await cls.objects.filter(key_id=key_id, company_id=company_id).update(
            last_used=datetime.now(timezone.utc)
        )
        if affected == 0:
            raise ValueError(f"API key {key_id} not found")

    @classmethod
    async def update_name(cls, key_id: str, company_id: str, name: str) -> bool:
        scoped_company_id = cls._require_company(company_id)
        affected = await cls.objects.filter(
            key_id=key_id,
            company_id=scoped_company_id,
        ).update(name=name)
        return affected > 0

    @classmethod
    async def revoke(cls, key_id: str, company_id: str) -> bool:
        scoped_company_id = cls._require_company(company_id)
        affected = await cls.objects.filter(
            key_id=key_id,
            company_id=scoped_company_id,
            revoked=False,
        ).update(revoked=True)
        return affected > 0
