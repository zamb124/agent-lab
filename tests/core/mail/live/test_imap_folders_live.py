"""Live IMAP folders: LIST + ensure idempotent on plt-* mailbox."""

from __future__ import annotations

import pytest

from core.mail.models import MailboxBindingKind, MailFolderRole
from core.mail.service import MailService

pytestmark = [pytest.mark.network, pytest.mark.timeout(180)]


@pytest.mark.asyncio
async def test_list_folders_has_inbox_and_ensure_idempotent(
    mail_live_service: MailService,
) -> None:
    _ = await mail_live_service.ensure_system_mail_connection()
    bindings = await mail_live_service.list_bindings(company_id="system")
    user_bindings = [
        binding
        for binding in bindings
        if binding.kind == MailboxBindingKind.USER
        and binding.email_address.lower().startswith("plt-")
    ]
    if not user_bindings:
        pytest.skip("no plt-* user binding on system company")
    binding = user_bindings[0]

    listed = await mail_live_service.list_folders(
        binding.mailbox_binding_id,
        company_id="system",
    )
    roles = {folder.role for folder in listed.folders}
    assert MailFolderRole.INBOX in roles
    assert any(folder.name.casefold() == "inbox" for folder in listed.folders)

    first = await mail_live_service.ensure_standard_folders(
        binding.mailbox_binding_id,
        company_id="system",
    )
    second = await mail_live_service.ensure_standard_folders(
        binding.mailbox_binding_id,
        company_id="system",
    )
    assert first.missing_standard_roles == []
    assert second.missing_standard_roles == []
    assert {folder.name for folder in first.folders} == {
        folder.name for folder in second.folders
    }
