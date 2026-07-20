"""Unit-тесты фильтра email-триггера и индексных helpers."""

from datetime import datetime, timezone

from apps.flows.src.models import EmailTriggerConfig
from apps.flows.src.triggers.email_filter import (
    email_message_matches_filter,
    email_trigger_index_key,
    email_trigger_index_member,
    inbound_mail_to_trigger_payload,
    parse_email_trigger_index_member,
)
from core.mail.models import InboundMailMessage, MailboxBinding, MailboxBindingKind


def _message(
    *,
    from_address: str | None = "alice@example.com",
    subject: str | None = "Hello world",
    body_text: str | None = "body",
    uid: str = "42",
) -> InboundMailMessage:
    return InboundMailMessage(
        uid=uid,
        message_id="<id@example.com>",
        subject=subject,
        from_address=from_address,
        body_text=body_text,
    )


def test_email_message_matches_filter_empty_means_all() -> None:
    config = EmailTriggerConfig(mailbox_binding_id="mailbind_1")
    assert email_message_matches_filter(config, _message()) is True


def test_email_message_matches_filter_allowed_senders_substring() -> None:
    config = EmailTriggerConfig(
        mailbox_binding_id="mailbind_1",
        allowed_senders=["alice@", "bob@"],
    )
    assert email_message_matches_filter(config, _message(from_address="Alice@Example.com")) is True
    assert email_message_matches_filter(config, _message(from_address="carol@example.com")) is False


def test_email_message_matches_filter_subject_contains() -> None:
    config = EmailTriggerConfig(
        mailbox_binding_id="mailbind_1",
        subject_contains="invoice",
    )
    assert email_message_matches_filter(config, _message(subject="Monthly Invoice #3")) is True
    assert email_message_matches_filter(config, _message(subject="Hello")) is False


def test_email_message_matches_filter_combined() -> None:
    config = EmailTriggerConfig(
        mailbox_binding_id="mailbind_1",
        allowed_senders=["billing@"],
        subject_contains="due",
    )
    assert (
        email_message_matches_filter(
            config,
            _message(from_address="billing@acme.com", subject="Payment due"),
        )
        is True
    )
    assert (
        email_message_matches_filter(
            config,
            _message(from_address="billing@acme.com", subject="Newsletter"),
        )
        is False
    )


def test_email_trigger_index_member_roundtrip() -> None:
    member = email_trigger_index_member(
        company_id="co1",
        flow_id="flow_a",
        trigger_id="inbox_mail",
    )
    assert parse_email_trigger_index_member(member) == ("co1", "flow_a", "inbox_mail")
    assert parse_email_trigger_index_member("broken") is None
    assert email_trigger_index_key("mailbind_x") == "flows:email_triggers:mailbind_x"


def test_inbound_mail_to_trigger_payload() -> None:
    now = datetime.now(timezone.utc)
    binding = MailboxBinding(
        mailbox_binding_id="mailbind_1",
        company_id="co1",
        company_mail_connection_id="conn1",
        user_id="user1",
        kind=MailboxBindingKind.USER,
        email_address="me@example.com",
        local_part="me",
        created_at=now,
        updated_at=now,
    )
    payload = inbound_mail_to_trigger_payload(
        binding=binding,
        message=_message(),
    )
    assert payload["from"] == "alice@example.com"
    assert payload["subject"] == "Hello world"
    assert payload["body"] == "body"
    assert payload["uid"] == "42"
    assert payload["mailbox_binding_id"] == "mailbind_1"
    assert payload["email_address"] == "me@example.com"
    assert payload["message_id"] == "<id@example.com>"
