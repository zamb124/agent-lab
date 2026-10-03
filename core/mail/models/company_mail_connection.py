"""Таблица почты."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar, Self, override

from oxyde import Field as DbField
from oxyde import Index
from oxyde.exceptions import IntegrityError
from pydantic import (
    ConfigDict,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from core.mail.models.contracts import (
    CONNECTION_UPSERT_MAX_ATTEMPTS,
    IspmanagerProvisionConfig,
    MailConnectionScope,
    MailConnectionStatus,
    MailProvider,
    mail_required,
)
from core.models.platform_model import PlatformModel
from core.types import JsonObject, require_serializer_json_object


class CompanyMailConnection(PlatformModel):
    """Подключение почтового сервера. Таблица ``company_mail_connections`` в ``platform_shared``.

    ``__global_model__``: синхронизация читает подключения всех компаний.
    Пароль ISPmanager в JSON не отдаётся.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    company_mail_connection_id: str = DbField(db_pk=True, max_length=255)

    class Meta:
        is_table: bool = True
        table_name: str = "company_mail_connections"
        indexes: list[Index] = [
            Index(("company_id",), unique=True, where="scope = 'company'"),
            Index(("mail_domain",)),
        ]

    company_id: str = DbField(db_index=True, max_length=255)
    scope: MailConnectionScope = DbField(
        default=MailConnectionScope.COMPANY,
        max_length=32,
        db_type="TEXT",
    )
    owner_user_id: str | None = DbField(default=None, db_index=True, max_length=255)
    mail_domain: str = DbField(max_length=255)
    provider: MailProvider = DbField(max_length=64, db_type="TEXT")
    imap_host: str = DbField(max_length=255)
    imap_port: int = DbField(ge=1, le=65535)
    smtp_host: str = DbField(max_length=255)
    smtp_port: int = DbField(ge=1, le=65535)
    use_ssl: bool = DbField(default=True)
    supports_provision: bool = DbField()
    status: MailConnectionStatus = DbField(
        default=MailConnectionStatus.ACTIVE,
        max_length=32,
        db_type="TEXT",
    )
    ispmanager: IspmanagerProvisionConfig | None = DbField(default=None, db_type="JSONB")
    created_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))

    @model_serializer(mode="wrap", when_used="json")
    def _json_without_isp_password(self, handler: SerializerFunctionWrapHandler) -> JsonObject:
        payload = require_serializer_json_object(handler, self, "CompanyMailConnection")
        ispmanager = payload.get("ispmanager")
        if isinstance(ispmanager, dict) and "authinfo_password_encrypted" in ispmanager:
            del ispmanager["authinfo_password_encrypted"]
        payload["has_ispmanager_auth"] = self.has_ispmanager_auth
        return payload

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        if self.company_mail_connection_id == "" or self.company_id == "" or self.mail_domain == "":
            raise ValueError("company_mail_connection_id, company_id and mail_domain are required")
        if self.scope == MailConnectionScope.COMPANY and self.owner_user_id is not None:
            raise ValueError("company mail connection cannot have owner_user_id")
        if self.scope == MailConnectionScope.PERSONAL and (
            self.owner_user_id is None or self.owner_user_id == ""
        ):
            raise ValueError("personal mail connection requires owner_user_id")
        self.updated_at = datetime.now(timezone.utc)

    @property
    def has_ispmanager_auth(self) -> bool:
        secret = None if self.ispmanager is None else self.ispmanager.authinfo_password_encrypted
        return secret is not None and secret.strip() != ""


    @classmethod
    async def for_company(cls, company_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=mail_required(company_id, "company_id"),
            scope=MailConnectionScope.COMPANY,
        ).get_or_none()

    @classmethod
    async def upsert_by_company_mail_connection_id(cls, connection: Self) -> Self:
        last_error: IntegrityError | None = None
        for _attempt in range(CONNECTION_UPSERT_MAX_ATTEMPTS):
            resolved = connection
            if connection.scope == MailConnectionScope.COMPANY:
                existing_company = await cls.for_company(connection.company_id)
                if (
                    existing_company is not None
                    and existing_company.company_mail_connection_id
                    != connection.company_mail_connection_id
                ):
                    resolved = connection.model_copy(
                        update={
                            "company_mail_connection_id": existing_company.company_mail_connection_id,
                            "created_at": existing_company.created_at,
                        }
                    )
            try:
                existing = await cls.get(resolved.company_mail_connection_id)
                if existing is None:
                    return await cls.objects.create(instance=resolved)
                existing.company_id = resolved.company_id
                existing.scope = resolved.scope
                existing.owner_user_id = resolved.owner_user_id
                existing.mail_domain = resolved.mail_domain
                existing.provider = resolved.provider
                existing.imap_host = resolved.imap_host
                existing.imap_port = resolved.imap_port
                existing.smtp_host = resolved.smtp_host
                existing.smtp_port = resolved.smtp_port
                existing.use_ssl = resolved.use_ssl
                existing.supports_provision = resolved.supports_provision
                existing.status = resolved.status
                existing.ispmanager = resolved.ispmanager
                existing.updated_at = resolved.updated_at
                _ = await existing.save()
                return existing
            except IntegrityError as exc:
                last_error = exc
                continue
        if last_error is None:
            raise RuntimeError("CompanyMailConnection upsert failed without IntegrityError")
        raise RuntimeError(
            "CompanyMailConnection upsert exhausted retries for "
            + f"company_id={connection.company_id}"
        ) from last_error
