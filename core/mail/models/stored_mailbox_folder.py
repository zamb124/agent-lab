"""Таблица почты."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar, Self, override

from oxyde import Field as DbField
from oxyde import Index, atomic
from pydantic import ConfigDict

from core.mail.models.contracts import (
    MailFolderRole,
    MailThreadResult,
    mail_required,
)
from core.models.platform_model import PlatformModel


class StoredMailboxFolder(PlatformModel):
    """Кэш IMAP-папки. Таблица ``mailbox_folders`` в ``platform_shared``.

    ``__global_model__``: список читается по ящику, не по активной компании запроса.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    mailbox_binding_id: str = DbField(db_index=True, max_length=255)
    folder_name: str = DbField(max_length=255)
    company_id: str = DbField(db_index=True, max_length=255)
    role: MailFolderRole = DbField(default=MailFolderRole.OTHER, max_length=32, db_type="TEXT")
    delimiter: str | None = DbField(default=None, max_length=16)
    flags: list[str] = DbField(default_factory=list, db_type="JSONB")
    selectable: bool = DbField(default=True)
    message_count: int = DbField(default=0, ge=0)
    unseen_count: int = DbField(default=0, ge=0)
    namespace_prefix: str = DbField(default="", max_length=255)
    capabilities: list[str] = DbField(default_factory=list, db_type="JSONB")
    sort_index: int = DbField(default=0)
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))
    mailbox_folder_id: str = DbField(default="", db_pk=True, max_length=512)

    class Meta:
        is_table: bool = True
        table_name: str = "mailbox_folders"
        indexes: list[Index] = [Index(("mailbox_binding_id", "folder_name"), unique=True)]

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        if self.mailbox_binding_id == "" or self.folder_name == "" or self.company_id == "":
            raise ValueError("mailbox_binding_id, folder_name and company_id are required")
        self.mailbox_folder_id = f"{self.mailbox_binding_id}:{self.folder_name}"
        self.updated_at = datetime.now(timezone.utc)


    @classmethod
    async def list_for_binding_by_sort_index_and_folder_name_asc(cls, mailbox_binding_id: str) -> list[Self]:
        """Папки привязки, ORDER BY sort_index, folder_name ASC. Предела нет. Пустой mailbox_binding_id — ValueError mailbox_binding_id cannot be empty."""
        return await cls.objects.filter(
            mailbox_binding_id=mail_required(mailbox_binding_id, "mailbox_binding_id"),
        ).order_by("sort_index", "folder_name").all()

    @classmethod
    async def replace_for_binding(
        cls,
        mailbox_binding_id: str,
        *,
        company_id: str,
        folders: list[Self],
    ) -> list[Self]:
        binding_id = mail_required(mailbox_binding_id, "mailbox_binding_id")
        scoped_company_id = mail_required(company_id, "company_id")
        rows = [
            folder.model_copy(
                update={
                    "mailbox_binding_id": binding_id,
                    "company_id": scoped_company_id,
                }
            )
            for folder in folders
        ]
        async with atomic(using="shared"):
            _ = await cls.objects.filter(mailbox_binding_id=binding_id).delete()
            for row in rows:
                _ = await cls.objects.create(instance=row)
        return await cls.list_for_binding_by_sort_index_and_folder_name_asc(binding_id)

    @classmethod
    async def replace_sort_indices(
        cls,
        mailbox_binding_id: str,
        *,
        folder_name_to_index: dict[str, int],
    ) -> list[Self]:
        """Заменяет sort_index всех папок ящика. Пустая карта — ValueError. Набор имён не совпал с кэшем — ValueError."""
        binding_id = mail_required(mailbox_binding_id, "mailbox_binding_id")
        if len(folder_name_to_index) == 0:
            raise ValueError("folder_name_to_index is required")
        existing = await cls.list_for_binding_by_sort_index_and_folder_name_asc(binding_id)
        known = {folder.folder_name for folder in existing}
        payload_names = set(folder_name_to_index.keys())
        if known != payload_names:
            missing = sorted(known - payload_names)
            extra = sorted(payload_names - known)
            raise ValueError(
                f"folder_names must match cached folders exactly; missing={missing!r} extra={extra!r}"
            )
        async with atomic(using="shared"):
            for folder in existing:
                folder.sort_index = folder_name_to_index[folder.folder_name]
                _ = await folder.save()
        return await cls.list_for_binding_by_sort_index_and_folder_name_asc(binding_id)



_ = MailThreadResult.model_rebuild()
