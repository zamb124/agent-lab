"""Сборка MessageRead из сущностей БД (общая для API и handlers)."""

from __future__ import annotations

from datetime import datetime

from apps.sync.db.models import SyncMessage
from apps.sync.models.common import UserBrief
from apps.sync.models.messages import (
    ForwardedFromChannel,
    MessageContentModel,
    MessageContentType,
    MessageRead,
    MessageStatus,
    ReactionEntry,
    TextPlainContent,
)


def _normalize_reactions(raw: object) -> list[ReactionEntry]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("reactions должен быть массивом.")
    out: list[ReactionEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Элемент reactions должен быть объектом.")
        uid = item.get("user_id")
        em = item.get("emoji")
        cat = item.get("created_at")
        if not isinstance(uid, str) or not isinstance(em, str):
            raise ValueError("reactions: user_id и emoji обязательны.")
        if isinstance(cat, str):
            created = datetime.fromisoformat(cat.replace("Z", "+00:00"))
        elif isinstance(cat, datetime):
            created = cat
        else:
            raise ValueError("reactions: created_at некорректен.")
        out.append(ReactionEntry(user_id=uid, emoji=em, created_at=created))
    return out


def mentioned_user_ids_from_contents(contents: list[MessageContentModel]) -> list[str] | None:
    """Первый по order блок text/plain: поле mentions для API и realtime."""
    for c in sorted(contents, key=lambda x: x.order):
        if c.type != MessageContentType.TEXT_PLAIN:
            continue
        d = c.data
        if isinstance(d, TextPlainContent):
            return d.mentions
        raise ValueError("text/plain: ожидается TextPlainContent.")
    return None


def message_read_from_entity(
    *,
    m: SyncMessage,
    contents: list[MessageContentModel],
    sender: UserBrief,
) -> MessageRead:
    forwarded_from = None
    fid = m.forwarded_from_channel_id
    if isinstance(fid, str) and fid != "":
        forwarded_from = ForwardedFromChannel(
            channel_id=fid,
            channel_name=m.forwarded_from_channel_name,
        )
    mids = mentioned_user_ids_from_contents(contents)
    return MessageRead(
        id=m.message_id,
        channel_id=m.channel_id,
        thread_id=m.thread_id,
        parent_message_id=m.parent_message_id,
        sender=sender,
        status=MessageStatus(m.status),
        sent_at=m.sent_at,
        edited_at=m.edited_at,
        contents=contents,
        reactions=_normalize_reactions(m.reactions),
        forwarded_from=forwarded_from,
        mentioned_user_ids=mids,
        call_id=m.call_id,
    )
