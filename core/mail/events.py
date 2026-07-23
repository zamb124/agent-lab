"""Каталог событий почты на шине `platform:events`."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from core.events import register_platform_event
from core.types import JsonObject

MAIL_MESSAGE_UPSERTED = "mail/message/upserted"
MAIL_MESSAGE_MOVED = "mail/message/moved"
MAIL_MESSAGE_REMOVED = "mail/message/removed"
MAIL_MESSAGE_SEND_SUCCEEDED = "mail/message/send_succeeded"
MAIL_MESSAGE_SEND_FAILED = "mail/message/send_failed"


class MailMessageUpsertedEventPayload(BaseModel):
    """Payload `mail/message/upserted`."""

    mailbox_binding_id: str
    folder: str
    uid: int
    unread_delta: int
    flagged: bool
    thread_id: str | None = None
    message_id: str | None = None
    list_item: JsonObject | None = None


class MailMessageMovedEventPayload(BaseModel):
    """Payload `mail/message/moved` — dump результата move/trash/archive."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    mailbox_binding_id: str | None = None


class MailMessageRemovedEventPayload(BaseModel):
    """Payload `mail/message/removed`."""

    mailbox_binding_id: str
    folder: str
    uid: int


class MailMessageSendSucceededEventPayload(BaseModel):
    """Payload `mail/message/send_succeeded`."""

    mailbox_binding_id: str
    message_id: str | None = None
    accepted: list[str] = Field(default_factory=list)


class MailMessageSendFailedEventPayload(BaseModel):
    """Payload `mail/message/send_failed`."""

    mailbox_binding_id: str
    error_detail: str


register_platform_event(
    MAIL_MESSAGE_UPSERTED,
    MailMessageUpsertedEventPayload,
    description="Новое или обновлённое письмо в ящике платформенной почты.",
)
register_platform_event(
    MAIL_MESSAGE_MOVED,
    MailMessageMovedEventPayload,
    description="Письмо перемещено (move/trash/archive).",
)
register_platform_event(
    MAIL_MESSAGE_REMOVED,
    MailMessageRemovedEventPayload,
    description="Письмо удалено из ящика.",
)
register_platform_event(
    MAIL_MESSAGE_SEND_SUCCEEDED,
    MailMessageSendSucceededEventPayload,
    description="Исходящее письмо успешно отправлено.",
)
register_platform_event(
    MAIL_MESSAGE_SEND_FAILED,
    MailMessageSendFailedEventPayload,
    description="Ошибка отправки исходящего письма.",
)
