"""MailAttachmentFileIndex: Storage принимает только JSON-строку."""

from __future__ import annotations

import pytest

from core.db.storage import Storage
from core.mail.attachment_index import MailAttachmentFileIndex


@pytest.mark.asyncio
async def test_mail_attachment_file_index_roundtrip(
    storage_shared: Storage,
    unique_id: str,
) -> None:
    index = MailAttachmentFileIndex(storage=storage_shared)
    mailbox_binding_id = f"mb_{unique_id}"
    mail_uid = f"uid_{unique_id}"
    file_id = f"file_{unique_id}"

    assert (
        await index.get(
            mailbox_binding_id=mailbox_binding_id,
            mail_uid=mail_uid,
            attachment_index=0,
        )
        is None
    )

    await index.set(
        mailbox_binding_id=mailbox_binding_id,
        mail_uid=mail_uid,
        attachment_index=0,
        file_id=file_id,
    )

    loaded = await index.get(
        mailbox_binding_id=mailbox_binding_id,
        mail_uid=mail_uid,
        attachment_index=0,
    )
    assert loaded == file_id
