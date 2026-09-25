"""Отображаемое имя отправителя сообщения (пользователь платформы или гость по guest:…:name)."""

from __future__ import annotations

from apps.sync.models.common import UserBrief
from core.models.identity_models import User


def guest_display_name_from_sender_id(sender_user_id: str) -> str | None:
    if not sender_user_id.startswith("guest:"):
        return None
    parts = sender_user_id.split(":", 2)
    if len(parts) >= 3 and parts[2].strip() != "":
        return parts[2]
    return "guest"


UNKNOWN_SPEAKER_DISPLAY_NAME = "guest"


async def sender_brief_for_message(
    sender_user_id: str,
    *,
    resolve_user: bool,
) -> UserBrief:
    guest_name = guest_display_name_from_sender_id(sender_user_id)
    if guest_name is not None:
        return UserBrief(user_id=sender_user_id, display_name=guest_name, avatar_url=None)
    if sender_user_id.strip() == "":
        raise ValueError("sender_user_id is empty.")
    if resolve_user:
        u = await User.get(sender_user_id)
        if u is not None:
            return UserBrief(user_id=sender_user_id, display_name=u.name, avatar_url=u.avatar_url)
    return UserBrief(
        user_id=sender_user_id,
        display_name=UNKNOWN_SPEAKER_DISPLAY_NAME,
        avatar_url=None,
    )
