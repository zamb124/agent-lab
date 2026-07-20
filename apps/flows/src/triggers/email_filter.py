"""
Фильтр и payload для email-триггеров на platform mail.
"""

from __future__ import annotations

from apps.flows.src.models import EmailTriggerConfig
from core.mail.models import InboundMailMessage, MailboxBinding
from core.types import JsonObject


def email_trigger_index_key(mailbox_binding_id: str) -> str:
    return f"flows:email_triggers:{mailbox_binding_id}"


def email_trigger_index_member(*, company_id: str, flow_id: str, trigger_id: str) -> str:
    return f"{company_id}|{flow_id}|{trigger_id}"


def parse_email_trigger_index_member(member: str) -> tuple[str, str, str] | None:
    parts = member.split("|", 2)
    if len(parts) != 3:
        return None
    company_id, flow_id, trigger_id = parts
    if not company_id or not flow_id or not trigger_id:
        return None
    return company_id, flow_id, trigger_id


def email_message_matches_filter(
    config: EmailTriggerConfig,
    message: InboundMailMessage,
) -> bool:
    from_address = message.from_address if message.from_address is not None else ""
    from_lower = from_address.lower()
    senders = [item.strip().lower() for item in config.allowed_senders if item.strip()]
    if senders:
        if not any(sender in from_lower for sender in senders):
            return False

    subject_needle = config.subject_contains.strip().lower()
    if subject_needle:
        subject = message.subject if message.subject is not None else ""
        if subject_needle not in subject.lower():
            return False
    return True


def inbound_mail_to_trigger_payload(
    *,
    binding: MailboxBinding,
    message: InboundMailMessage,
) -> JsonObject:
    from_address = message.from_address if message.from_address is not None else ""
    subject = message.subject if message.subject is not None else ""
    body = message.body_text if message.body_text is not None else ""
    payload: JsonObject = {
        "from": from_address,
        "subject": subject,
        "body": body,
        "uid": message.uid,
        "mailbox_binding_id": binding.mailbox_binding_id,
        "email_address": binding.email_address,
    }
    if message.message_id is not None:
        payload["message_id"] = message.message_id
    return payload


__all__ = [
    "email_message_matches_filter",
    "email_trigger_index_key",
    "email_trigger_index_member",
    "inbound_mail_to_trigger_payload",
    "parse_email_trigger_index_member",
]
