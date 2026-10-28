"""Strict contracts for revocable live Flow UI session sharing."""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from typing import ClassVar, Literal, Self

from oxyde import Field as DbField
from oxyde import Index
from pydantic import ConfigDict, Field, model_validator

from core.models.base import StrictBaseModel
from core.models.platform_model import PlatformModel

FlowUISharePermission = Literal["viewer", "editor"]


class FlowUIShareGrant(PlatformModel):
    """Живой грант шаринга сессии Flow UI. Таблица ``flow_ui_share_grants``."""

    __database_alias__: ClassVar[str | None] = "flows"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    class Meta:
        is_table: bool = True
        table_name: str = "flow_ui_share_grants"
        indexes: list[Index] = [
            Index(["company_id", "context_id"]),
            Index(["expires_at", "revoked_at"]),
        ]

    grant_id: str = DbField(db_pk=True, min_length=24)
    company_id: str = DbField(db_index=True, min_length=1)
    flow_id: str = DbField(min_length=1)
    branch_id: str = DbField(min_length=1)
    context_id: str = DbField(min_length=1)
    permission: FlowUISharePermission = DbField(db_type="TEXT")
    created_by_user_id: str = DbField(min_length=1)
    expires_at: datetime = DbField()
    created_at: datetime = DbField()
    redacted_paths: list[str] = DbField(
        default_factory=list,
        description="JSON Pointers полей state, скрытых от посетителя share",
    )
    revoked_at: datetime | None = DbField(default=None)

    @model_validator(mode="after")
    def bind_utc_timestamps(self) -> Self:
        if self.expires_at.tzinfo is None:
            self.expires_at = self.expires_at.replace(tzinfo=UTC)
        if self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=UTC)
        if self.revoked_at is not None and self.revoked_at.tzinfo is None:
            self.revoked_at = self.revoked_at.replace(tzinfo=UTC)
        return self

    @classmethod
    async def active_for_grant(cls, grant_id: str) -> Self | None:
        if grant_id == "":
            raise ValueError("grant_id is required")
        return await cls.objects.filter(
            grant_id=grant_id,
            revoked_at=None,
            expires_at__gt=datetime.now(timezone.utc),
        ).get_or_none()

    @classmethod
    async def list_for_owner(
        cls,
        *,
        company_id: str,
        flow_id: str,
        context_id: str,
        created_by_user_id: str,
    ) -> list[Self]:
        if company_id == "" or flow_id == "" or context_id == "" or created_by_user_id == "":
            raise ValueError("share list scope is required")
        return await (
            cls.objects.filter(
                company_id=company_id,
                flow_id=flow_id,
                context_id=context_id,
                created_by_user_id=created_by_user_id,
            )
            .order_by("-created_at")
            .all()
        )

    @classmethod
    async def list_unrevoked(cls, *, limit: int | None) -> list[Self]:
        if limit is not None and limit < 1:
            return []
        query = cls.objects.filter(revoked_at=None).order_by("grant_id")
        if limit is not None:
            query = query.limit(limit)
        return await query.all()

    @classmethod
    async def revoke_by_creator(
        cls,
        *,
        grant_id: str,
        company_id: str,
        created_by_user_id: str,
    ) -> bool:
        """Нет гранта, чужая компания, другой автор или уже отозванный — False. Иначе пишет revoked_at и возвращает True."""
        grant = await cls.get(grant_id)
        if grant is None:
            return False
        if grant.company_id != company_id or grant.created_by_user_id != created_by_user_id:
            return False
        if grant.revoked_at is not None:
            return False
        grant.revoked_at = datetime.now(timezone.utc)
        _ = await grant.save(update_fields=["revoked_at"])
        return True


class FlowUIShareCreateRequest(StrictBaseModel):
    flow_id: str = Field(min_length=1)
    context_id: str = Field(min_length=1)
    permission: FlowUISharePermission = "viewer"
    redacted_paths: list[str] = Field(default_factory=list)
    expires_in_seconds: int = Field(default=86_400, ge=300, le=2_592_000)


class FlowUIShareCreateResponse(StrictBaseModel):
    grant: FlowUIShareGrant
    share_url: str = Field(min_length=1)


class FlowUIShareExchangeResponse(StrictBaseModel):
    token: str = Field(min_length=1)
    token_type: Literal["Bearer"] = "Bearer"
    expires_at: datetime
    flow_id: str
    branch_id: str
    context_id: str
    permission: FlowUISharePermission
    redacted_paths: list[str] = Field(default_factory=list)
    flows_base_url: str = Field(min_length=1)


class FlowUIShareListPayload(StrictBaseModel):
    flow_id: str = Field(min_length=1)
    context_id: str = Field(min_length=1)


class FlowUIShareCreatePayload(FlowUIShareCreateRequest):
    public_host: str = ""


class FlowUIShareGrantIdPayload(StrictBaseModel):
    grant_id: str = Field(min_length=1)


class FlowUIShareDeletedResponse(StrictBaseModel):
    status: Literal["deleted"]
    grant_id: str


__all__ = [
    "FlowUIShareCreatePayload",
    "FlowUIShareCreateRequest",
    "FlowUIShareCreateResponse",
    "FlowUIShareDeletedResponse",
    "FlowUIShareExchangeResponse",
    "FlowUIShareGrant",
    "FlowUIShareGrantIdPayload",
    "FlowUIShareListPayload",
    "FlowUISharePermission",
]
