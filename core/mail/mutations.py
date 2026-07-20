"""Mail triage / draft / sync-now mutation helpers (imported by MailService methods)."""

from __future__ import annotations

from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from core.mail.models import (
    MailDraftSavePayload,
    MailDraftSaveResult,
    MailFolderRole,
    MailImapSystemFlag,
    MailMessageMovePayload,
    MailMessageMoveResult,
    MailMessageStarPayload,
    MailMessageStarResult,
    MailSyncNowPayload,
    MailSyncNowResult,
    OutboundMailMessage,
)


def build_rfc822_bytes(message: OutboundMailMessage, *, from_address: str) -> bytes:
    mime = EmailMessage()
    mime["From"] = from_address
    if message.to_addresses:
        mime["To"] = ", ".join(message.to_addresses)
    mime["Subject"] = message.subject
    message_id = message.message_id
    if message_id is None:
        message_id = make_msgid(domain=from_address.split("@", 1)[1])
    mime["Message-ID"] = message_id
    mime["Date"] = formatdate(localtime=True)
    if message.in_reply_to is not None:
        mime["In-Reply-To"] = message.in_reply_to
    if message.references is not None:
        mime["References"] = message.references
    if message.body_html is not None and message.body_html.strip():
        mime.set_content(message.body_text)
        mime.add_alternative(message.body_html, subtype="html")
    else:
        mime.set_content(message.body_text)
    for attachment in message.attachments:
        if not attachment.content:
            raise ValueError(
                f"outbound attachment content required filename={attachment.filename!r}"
            )
        maintype, _, subtype = attachment.content_type.partition("/")
        if not subtype:
            maintype = "application"
            subtype = "octet-stream"
        mime.add_attachment(
            attachment.content,
            maintype=maintype,
            subtype=subtype,
            filename=attachment.filename,
        )
    return mime.as_bytes()


__all__ = [
    "MailDraftSavePayload",
    "MailDraftSaveResult",
    "MailFolderRole",
    "MailImapSystemFlag",
    "MailMessageMovePayload",
    "MailMessageMoveResult",
    "MailMessageStarPayload",
    "MailMessageStarResult",
    "MailSyncNowPayload",
    "MailSyncNowResult",
    "build_rfc822_bytes",
]
