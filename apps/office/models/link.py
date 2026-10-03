"""Публичная ссылка каталога или файла. Одна ссылка на цель."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import ClassVar, Literal, Self

from oxyde import Field as DbField
from oxyde import Index as OxydeIndex

from core.models.platform_model import PlatformModel

LinkTargetKind = Literal["catalog", "file"]


class DocumentLink(PlatformModel):
    __database_alias__: ClassVar[str | None] = "office"
    __global_model__: ClassVar[bool] = True

    link_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100, db_index=True)
    target_kind: str = DbField(max_length=16)
    target_id: str = DbField(max_length=128)
    enabled: bool = DbField(default=False)
    token_hash: str | None = DbField(default=None, max_length=128)
    permission: str = DbField(default="viewer", max_length=16)
    created_by_user_id: str = DbField(max_length=100)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    class Meta:
        is_table: bool = True
        table_name: str = "document_links"
        indexes: list[OxydeIndex] = [
            OxydeIndex(["target_kind", "target_id"], unique=True),
            OxydeIndex(["token_hash"], unique=True, where="token_hash IS NOT NULL"),
        ]

    @classmethod
    async def for_target(cls, target_kind: str, target_id: str) -> Self | None:
        return await cls.objects.filter(target_kind=target_kind, target_id=target_id).get_or_none()

    @classmethod
    async def by_enabled_token(cls, token_hash: str) -> Self | None:
        return await cls.objects.filter(token_hash=token_hash, enabled=True).get_or_none()

    @classmethod
    async def ensure(
        cls,
        *,
        company_id: str,
        target_kind: str,
        target_id: str,
        created_by_user_id: str,
    ) -> Self:
        existing = await cls.for_target(target_kind, target_id)
        if existing is not None:
            return existing
        now = datetime.now(timezone.utc)
        return await cls.objects.create(
            instance=cls(
                link_id=uuid.uuid4().hex,
                company_id=company_id,
                target_kind=target_kind,
                target_id=target_id,
                enabled=False,
                token_hash=None,
                permission="viewer",
                created_by_user_id=created_by_user_id,
                created_at=now,
                updated_at=now,
            )
        )

    @classmethod
    async def save_state(
        cls,
        link: Self,
        *,
        enabled: bool,
        token_hash: str | None,
        permission: str,
    ) -> Self:
        link.enabled = enabled
        link.token_hash = token_hash
        link.permission = permission
        link.updated_at = datetime.now(timezone.utc)
        _ = await link.save()
        return link
