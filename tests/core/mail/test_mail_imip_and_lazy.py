"""Offline: iMIP parse + lazy get_or_create."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.mail.imip import (
    build_outbound_imip_invite,
    calendar_upsert_payload_from_imip,
    extract_imip_ics,
)
from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    InboundMailMessage,
    MailProvider,
)
from core.mail.service import MailService
from tests.core.mail.fakes import RecordingMailServerPort


def test_imip_build_and_parse_roundtrip() -> None:
    start_at = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)
    end_at = start_at + timedelta(hours=1)
    message, event_uid = build_outbound_imip_invite(
        to_address="att@linnex.io",
        organizer_email="org@linnex.io",
        title="Standup",
        description="daily",
        start_at=start_at,
        end_at=end_at,
        event_uid="uid-fixed-1",
    )
    assert event_uid == "uid-fixed-1"
    assert len(message.attachments) == 1
    inbound = InboundMailMessage(
        uid="1",
        subject=message.subject,
        body_text=message.body_text,
        attachments=list(message.attachments),
    )
    ics = extract_imip_ics(inbound)
    assert ics is not None
    payload = calendar_upsert_payload_from_imip(
        ics,
        attendee_email="att@linnex.io",
        mailbox_binding_id="mailbind_imip_test",
    )
    assert payload.title == "Standup"
    assert payload.metadata["imip_uid"] == "uid-fixed-1"
    assert payload.attendees[0].email == "att@linnex.io"
    assert payload.mailbox_binding_id == "mailbind_imip_test"
    # Дедуп-ключ iMIP: source_id = imip:{uid} (используется upsert_imip_event).
    assert payload.source_id == "imip:uid-fixed-1"
    # use_enum_values=True: payload.source в рантайме — строка, а не enum.
    # upsert_imip_event полагается на это (source в get_by_source без .value;
    # ранее .value ронял mail_sync_binding через AttributeError).
    assert payload.source == "platform"
    assert isinstance(payload.source, str)
    assert not hasattr(payload.source, "value")
    # use_enum_values=True: payload.source в рантайме — строка, а не enum.
    # upsert_imip_event полагается на это (source передаётся в get_by_source
    # без .value; ранее .value ронял mail_sync_binding через AttributeError).
    assert payload.source == "platform"
    assert isinstance(payload.source, str)
    assert not hasattr(payload.source, "value")


@pytest.mark.asyncio
async def test_get_or_create_user_binding_lazy(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    unique_id: str,
) -> None:
    company_id = f"maillazy_{unique_id}"
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.example.com",
            provider=MailProvider.ISPMANAGER,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            ispmanager_base_url="https://panel.example.com/ispmgr",
            ispmanager_authinfo_user="admin",
            ispmanager_authinfo_password="secret",
        ),
        company_id=company_id,
    )
    user_id = f"user_{unique_id}"
    first = await mail_service.get_or_create_user_binding(
        user_id,
        company_id=company_id,
        local_part=f"u.{unique_id}",
    )
    second = await mail_service.get_or_create_user_binding(
        user_id,
        company_id=company_id,
    )
    assert first.mailbox_binding_id == second.mailbox_binding_id
    assert len(recording_mail_port.ensure_calls) >= 1
