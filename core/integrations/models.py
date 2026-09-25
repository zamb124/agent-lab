"""
Доменные модели универсального механизма интеграций.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import ClassVar, Self, override

from oxyde import Field as DbField
from pydantic import ConfigDict, SerializerFunctionWrapHandler, model_serializer

from core.models.base import StrictBaseModel
from core.models.platform_model import PlatformModel
from core.types import JsonObject, require_serializer_json_object


class IntegrationProvider(StrEnum):
    GOOGLE = "google"
    YANDEX = "yandex"
    MAILRU = "mailru"
    CALDAV = "caldav"
    AMOCRM = "amocrm"


class IntegrationCredential(PlatformModel):
    """OAuth-токен пользователя. Таблица ``integration_credentials`` в ``platform_shared``.

    ``__global_model__``: пакетная синхронизация читает провайдера без компании запроса.
    Токены в JSON не отдаются.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    credential_id: str = DbField(db_pk=True, max_length=255)

    class Meta:
        is_table: bool = True
        table_name: str = "integration_credentials"

    company_id: str = DbField(db_index=True, max_length=255)
    user_id: str = DbField(db_index=True, max_length=255)
    provider: IntegrationProvider = DbField(db_index=True, max_length=64)
    service: str = DbField(db_index=True, max_length=64)
    mailbox_binding_id: str | None = DbField(default=None, db_index=True, max_length=255)
    access_token: str = DbField(db_type="TEXT")
    refresh_token: str | None = DbField(default=None, db_type="TEXT")
    expires_at: datetime | None = DbField(default=None)
    scope: str | None = DbField(default=None, db_type="TEXT")
    token_type: str | None = DbField(default=None, max_length=64)
    metadata: JsonObject = DbField(default_factory=dict, db_type="JSONB")
    created_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))

    @model_serializer(mode="wrap", when_used="json")
    def _json_without_tokens(self, handler: SerializerFunctionWrapHandler) -> JsonObject:
        payload = require_serializer_json_object(handler, self, "IntegrationCredential")
        if "access_token" in payload:
            del payload["access_token"]
        if "refresh_token" in payload:
            del payload["refresh_token"]
        return payload

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        if self.credential_id == "" or self.company_id == "" or self.user_id == "" or self.service == "":
            raise ValueError("credential_id, company_id, user_id and service are required")
        if self.access_token == "":
            raise ValueError("access_token cannot be empty.")
        self.updated_at = datetime.now(timezone.utc)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= expires_at

    @classmethod
    async def by_natural_key(
        cls,
        *,
        company_id: str,
        user_id: str,
        provider: IntegrationProvider,
        service: str,
        mailbox_binding_id: str | None,
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=_required_credential_field(company_id, "company_id"),
            user_id=_required_credential_field(user_id, "user_id"),
            provider=provider,
            service=_required_credential_field(service, "service"),
            mailbox_binding_id=mailbox_binding_id,
        ).get_or_none()

    @classmethod
    async def find_for_user(
        cls,
        company_id: str,
        user_id: str,
        credential_id: str,
    ) -> Self | None:
        return await cls.objects.filter(
            credential_id=_required_credential_field(credential_id, "credential_id"),
            company_id=_required_credential_field(company_id, "company_id"),
            user_id=_required_credential_field(user_id, "user_id"),
        ).get_or_none()

    @classmethod
    async def list_by_user_provider_service(
        cls,
        company_id: str,
        user_id: str,
        provider: IntegrationProvider,
        service: str,
    ) -> list[Self]:
        return await cls.objects.filter(
            company_id=_required_credential_field(company_id, "company_id"),
            user_id=_required_credential_field(user_id, "user_id"),
            provider=provider,
            service=_required_credential_field(service, "service"),
        ).order_by("created_at").all()

    @classmethod
    async def list_by_user(
        cls,
        company_id: str,
        user_id: str,
    ) -> list[Self]:
        return await cls.objects.filter(
            company_id=_required_credential_field(company_id, "company_id"),
            user_id=_required_credential_field(user_id, "user_id"),
        ).order_by("created_at").all()

    @classmethod
    async def list_by_provider_service(
        cls,
        provider: IntegrationProvider,
        service: str,
        *,
        limit: int = 500,
    ) -> list[Self]:
        return await cls.objects.filter(
            provider=provider,
            service=_required_credential_field(service, "service"),
        ).order_by("updated_at").limit(limit).all()

    @classmethod
    async def upsert_by_credential_id(cls, credential: Self) -> None:
        credential_id = _required_credential_field(credential.credential_id, "credential_id")
        clash = await cls.by_natural_key(
            company_id=credential.company_id,
            user_id=credential.user_id,
            provider=credential.provider,
            service=credential.service,
            mailbox_binding_id=credential.mailbox_binding_id,
        )
        if clash is not None and clash.credential_id != credential_id:
            raise ValueError(
                "integration credential already exists for this user, provider, service and mailbox"
            )
        existing = await cls.objects.filter(credential_id=credential_id).get_or_none()
        if existing is None:
            _ = await cls.objects.create(instance=credential)
            return
        if existing.company_id != credential.company_id or existing.user_id != credential.user_id:
            raise ValueError("credential_id belongs to another company or user")
        _ = await credential.save()

    @classmethod
    async def delete_by_credential_id(
        cls,
        credential_id: str,
        company_id: str,
        user_id: str,
    ) -> bool:
        deleted = await cls.objects.filter(
            credential_id=_required_credential_field(credential_id, "credential_id"),
            company_id=_required_credential_field(company_id, "company_id"),
            user_id=_required_credential_field(user_id, "user_id"),
        ).delete()
        return deleted > 0

    @classmethod
    async def delete_by_user_provider_service(
        cls,
        company_id: str,
        user_id: str,
        provider: IntegrationProvider,
        service: str,
    ) -> bool:
        deleted = await cls.objects.filter(
            company_id=_required_credential_field(company_id, "company_id"),
            user_id=_required_credential_field(user_id, "user_id"),
            provider=provider,
            service=_required_credential_field(service, "service"),
        ).delete()
        return deleted > 0

    @classmethod
    async def delete_by_mailbox_binding(
        cls,
        company_id: str,
        mailbox_binding_id: str,
        service: str,
    ) -> int:
        return await cls.objects.filter(
            company_id=_required_credential_field(company_id, "company_id"),
            mailbox_binding_id=_required_credential_field(mailbox_binding_id, "mailbox_binding_id"),
            service=_required_credential_field(service, "service"),
        ).delete()


def _required_credential_field(value: str, field_name: str) -> str:
    if value == "":
        raise ValueError(f"{field_name} cannot be empty.")
    return value


class CredentialInfo(StrictBaseModel):
    """Публичная проекция credential для UI (без токенов)."""

    provider: str
    service: str
    created_at: datetime


class IntegrationCredentialRefPayload(StrictBaseModel):
    provider: str = ""
    service: str = ""


class IntegrationDeletedResponse(StrictBaseModel):
    deleted: bool


class OAuthProviderConfig(StrictBaseModel):
    """Конфигурация OAuth2-провайдера, читается из settings.auth.providers."""

    provider: IntegrationProvider
    client_id: str
    client_secret: str
    auth_url: str
    token_url: str
    token_request_format: str = "form"
