"""MailboxBinding.calendar_color: default + owner/admin patch."""

from __future__ import annotations

import pytest

from core.mail.calendar_colors import default_calendar_color, require_mail_calendar_color
from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailboxBindingPatchPayload,
    MailProvider,
)
from core.mail.service import MailService, to_public_binding
from tests.core.mail.fakes import RecordingMailServerPort


def test_default_calendar_color_is_palette_key() -> None:
    color = default_calendar_color("alice@linnex.io")
    assert color == require_mail_calendar_color(color)


@pytest.mark.asyncio
async def test_bind_mailbox_sets_deterministic_calendar_color(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    unique_id: str,
) -> None:
    company_id = f"mailcolor_{unique_id}"
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.example.test",
            provider=MailProvider.GENERIC_IMAP_SMTP,
            imap_host="imap.example.test",
            imap_port=993,
            smtp_host="smtp.example.test",
            smtp_port=465,
            use_ssl=True,
        ),
        company_id=company_id,
    )
    email = f"box@{unique_id}.example.test"
    binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=f"user_{unique_id}",
            email_address=email,
            provision=False,
            sync_enabled=True,
            is_default=True,
        ),
        company_id=company_id,
    )
    assert binding.calendar_color == default_calendar_color(email)
    public = to_public_binding(binding)
    assert public.calendar_color == binding.calendar_color


@pytest.mark.asyncio
async def test_patch_calendar_color_by_owner(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = f"mailcolor_patch_{unique_id}"
    user_id = f"owner_{unique_id}"
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"p{unique_id}.example.test",
            provider=MailProvider.GENERIC_IMAP_SMTP,
            imap_host="imap.example.test",
            imap_port=993,
            smtp_host="smtp.example.test",
            smtp_port=465,
            use_ssl=True,
        ),
        company_id=company_id,
    )
    binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_id,
            local_part="owner",
            provision=False,
            sync_enabled=True,
            is_default=True,
        ),
        company_id=company_id,
    )
    monkeypatch.setattr(mail_service, "_active_user_id", lambda: user_id)
    monkeypatch.setattr(mail_service, "_is_company_admin", lambda _cid: False)
    patched = await mail_service.patch_binding(
        binding.mailbox_binding_id,
        MailboxBindingPatchPayload(calendar_color="mint"),
        company_id=company_id,
    )
    assert patched.calendar_color == "mint"
