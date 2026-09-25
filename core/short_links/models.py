"""Короткая ссылка. Таблица ``platform_short_links`` в ``platform_shared``."""

from datetime import datetime, timezone
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import execute_raw
from oxyde.exceptions import IntegrityError

from core.models.platform_model import PlatformModel
from core.short_links.kinds import SHORT_LINK_KIND_SYNC_CALL_JOIN
from core.short_links.payloads import ShortLinkPayload
from core.types import JsonObject, require_json_object


class PlatformShortLink(PlatformModel):
    """Публичный код. Полезная нагрузка зависит от ``kind`` и лежит в ``payload``."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    code: str = DbField(db_pk=True, max_length=32)

    class Meta:
        is_table: bool = True
        table_name: str = "platform_short_links"

    kind: str = DbField(db_index=True, max_length=64)
    payload: JsonObject = DbField(db_type="JSONB")
    expires_at: datetime = DbField(db_index=True)
    created_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    async def insert_try(
        cls,
        code: str,
        kind: str,
        payload: ShortLinkPayload,
        expires_at: datetime,
    ) -> bool:
        row = cls(
            code=code,
            kind=kind,
            payload=require_json_object(payload.model_dump(mode="json"), "short_link.payload"),
            expires_at=expires_at,
        )
        try:
            _ = await cls.objects.create(instance=row)
        except IntegrityError:
            return False
        return True

    @classmethod
    async def find_sync_by_link_token(cls, link_token: str) -> Self | None:
        rows = await execute_raw(
            """
            SELECT code, kind, payload, expires_at, created_at
            FROM platform_short_links
            WHERE kind = $1 AND payload->>'link_token' = $2
            LIMIT 2
            """,
            [SHORT_LINK_KIND_SYNC_CALL_JOIN, link_token],
            using="shared",
        )
        if len(rows) == 0:
            return None
        if len(rows) > 1:
            raise RuntimeError("multiple short links for one link_token")
        return cls.model_validate(require_json_object(rows[0], "platform_short_links"))

    @classmethod
    async def update_expires_at(cls, code: str, expires_at: datetime) -> None:
        row = await cls.get(code)
        if row is None:
            raise ValueError(f"Short link {code} not found")
        row.expires_at = expires_at
        _ = await row.save(update_fields=["expires_at"])

    @classmethod
    async def delete_by_code_and_kind_returning(
        cls,
        code: str,
        kind: str,
    ) -> Self | None:
        row = await cls.objects.filter(code=code, kind=kind).get_or_none()
        if row is None:
            return None
        deleted = await cls.objects.filter(code=code, kind=kind).delete()
        if deleted == 0:
            return None
        return row

    @classmethod
    async def delete_sync_by_link_token(cls, link_token: str) -> int:
        rows = await execute_raw(
            """
            DELETE FROM platform_short_links
            WHERE kind = $1 AND payload->>'link_token' = $2
            RETURNING code
            """,
            [SHORT_LINK_KIND_SYNC_CALL_JOIN, link_token],
            using="shared",
        )
        return len(rows)
