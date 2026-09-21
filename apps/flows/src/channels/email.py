"""
EmailChannelHandler — outbound email: platform mailbox или inline SMTP в ноде.
"""

from __future__ import annotations

from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Final, Literal, override

import aiosmtplib

from apps.flows.src.models.enums import ChannelType
from core.logging import get_logger
from core.mail.models import MailSendPayload
from core.mail.service import MailService
from core.state import ExecutionState
from core.types import JsonObject, JsonValue

from .base import BaseChannelHandler

logger = get_logger(__name__)

EmailDelivery = Literal["mailbox", "smtp"]

_SMTP_CONFIG_KEYS: Final[frozenset[str]] = frozenset(
    {
        "smtp_host",
        "smtp_port",
        "smtp_user",
        "from_email",
        "password",
        "smtp_use_tls",
    }
)


def _parse_to_addresses(recipient: str) -> list[str]:
    parts = [part.strip() for part in recipient.split(",")]
    addresses = [part for part in parts if part]
    if not addresses:
        raise ValueError("Channel action parameter 'recipient' must contain at least one email")
    return addresses


def _require_str_config(config: JsonObject, key: str) -> str:
    raw = config.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"Email channel_config.{key} must be a non-empty string")
    return raw.strip()


def _resolve_delivery(config: JsonObject) -> EmailDelivery:
    raw = config.get("delivery")
    if raw == "mailbox":
        return "mailbox"
    if raw == "smtp":
        return "smtp"
    if raw is None:
        raise ValueError("Email channel_config.delivery is required ('mailbox' or 'smtp')")
    raise ValueError(
        f"Email channel_config.delivery must be 'mailbox' or 'smtp', got {raw!r}"
    )


def _optional_kwarg_str(kwargs: dict[str, JsonValue], name: str) -> str | None:
    if name not in kwargs:
        return None
    value = kwargs[name]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Channel action parameter {name!r} must be a string")
    return value


def _smtp_port(config: JsonObject) -> int:
    raw = config.get("smtp_port")
    if raw is None:
        return 587
    if isinstance(raw, bool):
        raise ValueError("Email channel_config.smtp_port must be an integer")
    if isinstance(raw, int):
        if raw <= 0 or raw > 65535:
            raise ValueError("Email channel_config.smtp_port out of range")
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        port = int(raw.strip())
        if port <= 0 or port > 65535:
            raise ValueError("Email channel_config.smtp_port out of range")
        return port
    raise ValueError("Email channel_config.smtp_port must be an integer")


def _smtp_use_tls(config: JsonObject) -> bool:
    raw = config.get("smtp_use_tls")
    if raw is None:
        return True
    if isinstance(raw, bool):
        return raw
    raise ValueError("Email channel_config.smtp_use_tls must be a boolean")


async def send_smtp_message(
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    password: str,
    from_email: str,
    to_addresses: list[str],
    subject: str,
    body_text: str,
    body_html: str | None,
    in_reply_to: str | None,
    references: str | None,
    use_tls: bool,
) -> dict[str, JsonValue]:
    """Ad-hoc SMTP send (без platform mail_messages / Sent APPEND)."""
    domain = from_email.split("@", 1)[1] if "@" in from_email else "localhost"
    message_id = make_msgid(domain=domain)
    mime = EmailMessage()
    mime["From"] = from_email
    mime["To"] = ", ".join(to_addresses)
    mime["Subject"] = subject
    mime["Message-ID"] = message_id
    mime["Date"] = formatdate(localtime=True)
    if in_reply_to is not None:
        mime["In-Reply-To"] = in_reply_to
    if references is not None:
        mime["References"] = references
    if body_html is not None and body_html.strip():
        mime.set_content(body_text)
        mime.add_alternative(body_html, subtype="html")
    else:
        mime.set_content(body_text)

    smtp = aiosmtplib.SMTP(
        hostname=smtp_host,
        port=smtp_port,
        use_tls=use_tls,
        timeout=30.0,
    )
    try:
        _ = await smtp.connect()
        _ = await smtp.login(smtp_user, password)
        errors, response = await smtp.send_message(mime)
        if errors:
            raise ValueError(
                f"SMTP recipients refused for {from_email}: {errors!r} response={response!r}"
            )
    except aiosmtplib.SMTPException as exc:
        raise ValueError(f"SMTP send failed: {exc}") from exc
    finally:
        try:
            _ = await smtp.quit()
        except aiosmtplib.SMTPException:
            pass

    return {
        "message_id": message_id,
        "accepted": list(to_addresses),
    }


class EmailChannelHandler(BaseChannelHandler):
    """
    Outbound email: delivery=mailbox (MailService) или delivery=smtp (aiosmtplib).

    channel_config mailbox:
      { "delivery": "mailbox", "mailbox_binding_id": "mailbind_…" }

    channel_config smtp:
      {
        "delivery": "smtp",
        "smtp_host": "...",
        "smtp_port": 587,
        "from_email": "...",
        "password": "@var:smtp_password",
        "smtp_user": "...",   # optional, default = from_email
        "smtp_use_tls": true
      }

    send_message params:
      recipient (required), text (required), subject (string, may be empty)
    """

    channel_type: ChannelType = ChannelType.EMAIL

    def __init__(self, mail_service: MailService) -> None:
        self._mail_service: MailService = mail_service

    @override
    async def execute_action(
        self,
        action: str,
        params: JsonObject,
        config: JsonObject,
        variables: JsonObject,
        state: ExecutionState | JsonObject | None = None,
    ) -> JsonObject:
        _ = state
        if action != "send_message":
            raise ValueError(
                f"Unknown action '{action}' for channel email. Available: send_message"
            )
        recipient = self._require_str_param(params, "recipient")
        text = self._require_str_param(params, "text")
        subject_raw = params.get("subject")
        if subject_raw is None:
            subject = ""
        elif isinstance(subject_raw, str):
            subject = subject_raw
        else:
            raise ValueError("Channel action parameter 'subject' must be a string")
        kwargs = self._extra_params(params, {"recipient", "text", "subject"})
        return await self.send_message(
            recipient=recipient,
            text=text,
            config=config,
            variables=variables,
            subject=subject,
            **kwargs,
        )

    @override
    async def send_message(
        self,
        recipient: str,
        text: str,
        config: JsonObject,
        variables: JsonObject,
        **kwargs: JsonValue,
    ) -> JsonObject:
        _ = variables
        delivery = _resolve_delivery(config)
        to_addresses = _parse_to_addresses(recipient)
        subject_value = kwargs.get("subject")
        if subject_value is None:
            subject = ""
        elif isinstance(subject_value, str):
            subject = subject_value
        else:
            raise ValueError("Channel action parameter 'subject' must be a string")
        body_html = _optional_kwarg_str(kwargs, "body_html")
        in_reply_to = _optional_kwarg_str(kwargs, "in_reply_to")
        references = _optional_kwarg_str(kwargs, "references")

        if delivery == "mailbox":
            return await self._send_via_mailbox(
                config=config,
                to_addresses=to_addresses,
                subject=subject,
                body_text=text,
                body_html=body_html,
                in_reply_to=in_reply_to,
                references=references,
            )
        return await self._send_via_smtp(
            config=config,
            to_addresses=to_addresses,
            subject=subject,
            body_text=text,
            body_html=body_html,
            in_reply_to=in_reply_to,
            references=references,
        )

    async def _send_via_mailbox(
        self,
        *,
        config: JsonObject,
        to_addresses: list[str],
        subject: str,
        body_text: str,
        body_html: str | None,
        in_reply_to: str | None,
        references: str | None,
    ) -> JsonObject:
        for smtp_key in _SMTP_CONFIG_KEYS:
            if smtp_key in config:
                raise ValueError(
                    "Email delivery=mailbox forbids SMTP key "
                    + f"{smtp_key!r}; use delivery=smtp"
                )
        mailbox_binding_id = _require_str_config(config, "mailbox_binding_id")
        payload = MailSendPayload(
            mailbox_binding_id=mailbox_binding_id,
            to_addresses=to_addresses,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            in_reply_to=in_reply_to,
            references=references,
        )
        result = await self._mail_service.send_message(payload)
        logger.info(
            "flows.email.channel.send_message.delivery.mailbox",
            mailbox_binding_id=mailbox_binding_id,
            to=to_addresses,
            message_id=result.message_id,
        )
        return {
            "message_id": result.message_id,
            "accepted": list(result.accepted),
        }

    async def _send_via_smtp(
        self,
        *,
        config: JsonObject,
        to_addresses: list[str],
        subject: str,
        body_text: str,
        body_html: str | None,
        in_reply_to: str | None,
        references: str | None,
    ) -> JsonObject:
        if "mailbox_binding_id" in config:
            raise ValueError(
                "Email delivery=smtp forbids mailbox_binding_id; use delivery=mailbox"
            )
        smtp_host = _require_str_config(config, "smtp_host")
        from_email = _require_str_config(config, "from_email")
        password = _require_str_config(config, "password")
        smtp_user_raw = config.get("smtp_user")
        if smtp_user_raw is None or smtp_user_raw == "":
            smtp_user = from_email
        elif isinstance(smtp_user_raw, str) and smtp_user_raw.strip():
            smtp_user = smtp_user_raw.strip()
        else:
            raise ValueError("Email channel_config.smtp_user must be a string when set")
        port = _smtp_port(config)
        use_tls = _smtp_use_tls(config)
        result = await send_smtp_message(
            smtp_host=smtp_host,
            smtp_port=port,
            smtp_user=smtp_user,
            password=password,
            from_email=from_email,
            to_addresses=to_addresses,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            in_reply_to=in_reply_to,
            references=references,
            use_tls=use_tls,
        )
        logger.info(
            "flows.email.channel.send_message.delivery.smtp",
            host=smtp_host,
            from_value=from_email,
            to=to_addresses,
            message_id=result['message_id'],
        )
        return result

    @override
    async def send_photo(
        self,
        recipient: str,
        photo: str | bytes,
        config: JsonObject,
        variables: JsonObject,
        caption: str | None = None,
        **kwargs: JsonValue,
    ) -> JsonObject:
        _ = (recipient, photo, config, variables, caption, kwargs)
        raise ValueError("Email channel does not support send_photo")

    @override
    async def send_document(
        self,
        recipient: str,
        document: str | bytes,
        config: JsonObject,
        variables: JsonObject,
        caption: str | None = None,
        filename: str | None = None,
        **kwargs: JsonValue,
    ) -> JsonObject:
        _ = (recipient, document, config, variables, caption, filename, kwargs)
        raise ValueError("Email channel does not support send_document")


__all__ = ["EmailChannelHandler", "send_smtp_message"]
