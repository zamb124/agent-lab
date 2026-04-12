"""Отображаемое имя отправителя сообщения (пользователь платформы или гость по guest:…:name)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.sync.models.common import UserBrief

if TYPE_CHECKING:
    from core.db.repositories.user_repository import UserRepository


def guest_display_name_from_sender_id(sender_user_id: str) -> str | None:
    if not sender_user_id.startswith("guest:"):
        return None
    parts = sender_user_id.split(":", 2)
    if len(parts) >= 3 and parts[2].strip() != "":
        return parts[2]
    return "guest"


async def sender_brief_for_message(
    user_repository: UserRepository | None,
    sender_user_id: str,
) -> UserBrief:
    guest_name = guest_display_name_from_sender_id(sender_user_id)
    if guest_name is not None:
        return UserBrief(user_id=sender_user_id, display_name=guest_name, avatar_url=None)
    display_name = sender_user_id
    avatar_url = None
    if user_repository is not None:
        u = await user_repository.get(sender_user_id)
        if u is not None:
            display_name = u.name
            avatar_url = u.avatar_url
    return UserBrief(user_id=sender_user_id, display_name=display_name, avatar_url=avatar_url)
