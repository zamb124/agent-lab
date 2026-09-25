"""mailbox_folders.sort_index: bootstrap merge + reorder."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.mail.models import (
    MailFolder,
    MailFolderListResult,
    MailFolderRole,
    MailFoldersReorderPayload,
    PersonalMailboxConnectPayload,
    StoredMailboxFolder,
)
from core.mail.service import MailService
from tests.core.mail.conftest import seed_mail_company_member
from tests.core.mail.fakes import RecordingMailServerPort


@pytest.mark.asyncio
async def test_folder_sort_index_bootstrap_and_preserve_on_refresh(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    di,
    unique_id: str,
) -> None:
    _ = recording_mail_port
    company_id = f"mailsort_{unique_id}"
    user_id = f"user_{unique_id}"
    _ = await seed_mail_company_member(
        di,
        company_id=company_id,
        user_id=user_id,
        unique_id=unique_id,
    )
    binding = await mail_service.connect_personal_mailbox(
        PersonalMailboxConnectPayload(
            email_address=f"sort.{unique_id}@mail.ru",
            password="pass",
            imap_host="imap.mail.ru",
            imap_port=993,
            smtp_host="smtp.mail.ru",
            smtp_port=465,
        ),
        company_id=company_id,
    )
    folders = await mail_service.list_folders(
        binding.mailbox_binding_id,
        company_id=company_id,
    )
    assert folders.folders
    names_before = [folder.name for folder in folders.folders]
    indices_before = {folder.name: folder.sort_index for folder in folders.folders}

    reordered = list(reversed(names_before))
    ordered = await mail_service.reorder_folders(
        MailFoldersReorderPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder_names=reordered,
        ),
        company_id=company_id,
    )
    assert [folder.name for folder in ordered.folders] == reordered
    assert [folder.sort_index for folder in ordered.folders] == list(range(len(reordered)))

    await mail_service.refresh_folders_from_imap(
        binding.mailbox_binding_id,
        company_id=company_id,
    )
    after_refresh = await mail_service.list_folders(
        binding.mailbox_binding_id,
        company_id=company_id,
    )
    assert [folder.name for folder in after_refresh.folders] == reordered
    for folder in after_refresh.folders:
        assert folder.sort_index == reordered.index(folder.name)

    assert indices_before != {folder.name: folder.sort_index for folder in after_refresh.folders}


@pytest.mark.asyncio
async def test_persist_folder_cache_assigns_new_folder_after_max(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    di,
    unique_id: str,
) -> None:
    _ = recording_mail_port
    company_id = f"mailmerge_{unique_id}"
    user_id = f"user_{unique_id}"
    _ = await seed_mail_company_member(
        di,
        company_id=company_id,
        user_id=user_id,
        unique_id=unique_id,
    )
    binding = await mail_service.connect_personal_mailbox(
        PersonalMailboxConnectPayload(
            email_address=f"merge.{unique_id}@mail.ru",
            password="pass",
            imap_host="imap.mail.ru",
            imap_port=993,
            smtp_host="smtp.mail.ru",
            smtp_port=465,
        ),
        company_id=company_id,
    )
    existing = await StoredMailboxFolder.list_for_binding(binding.mailbox_binding_id)
    assert existing
    now = datetime.now(timezone.utc)
    seeded = [
        StoredMailboxFolder(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder_name="INBOX",
            company_id=company_id,
            role=MailFolderRole.INBOX,
            selectable=True,
            sort_index=0,
            updated_at=now,
        ),
        StoredMailboxFolder(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder_name="Sent",
            company_id=company_id,
            role=MailFolderRole.SENT,
            selectable=True,
            sort_index=5,
            updated_at=now,
        ),
    ]
    _ = await StoredMailboxFolder.replace_for_binding(
        binding.mailbox_binding_id,
        company_id=company_id,
        folders=seeded,
    )
    await mail_service._persist_folder_cache(
        binding,
        MailFolderListResult(
            folders=[
                MailFolder(name="INBOX", role=MailFolderRole.INBOX),
                MailFolder(name="Sent", role=MailFolderRole.SENT),
                MailFolder(name="Custom", role=MailFolderRole.OTHER),
            ],
        ),
    )
    stored = await StoredMailboxFolder.list_for_binding(binding.mailbox_binding_id)
    by_name = {item.folder_name: item.sort_index for item in stored}
    assert by_name["INBOX"] == 0
    assert by_name["Sent"] == 5
    assert by_name["Custom"] == 6
