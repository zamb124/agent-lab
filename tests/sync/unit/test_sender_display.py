"""sender_brief_for_message: guest:* и неизвестный id — гостевое display_name."""

from __future__ import annotations

import pytest

from apps.sync.sender_display import (
    UNKNOWN_SPEAKER_DISPLAY_NAME,
    guest_display_name_from_sender_id,
    sender_brief_for_message,
)


@pytest.mark.asyncio
async def test_sender_brief_guest_identity_uses_name_from_id() -> None:
    brief = await sender_brief_for_message(None, "guest:aabbccdd:Алиса")
    assert brief.user_id == "guest:aabbccdd:Алиса"
    assert brief.display_name == "Алиса"
    assert brief.avatar_url is None


@pytest.mark.asyncio
async def test_sender_brief_unknown_id_uses_guest_display_name() -> None:
    brief = await sender_brief_for_message(None, "lk_unknown_track")
    assert brief.user_id == "lk_unknown_track"
    assert brief.display_name == UNKNOWN_SPEAKER_DISPLAY_NAME
    assert brief.display_name != "lk_unknown_track"
    assert brief.avatar_url is None


def test_guest_display_name_without_name_part() -> None:
    assert guest_display_name_from_sender_id("guest:aabbccdd") == "guest"
