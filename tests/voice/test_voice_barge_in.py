"""Тесты BargeInController."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.voice.services.voice_barge_in import BargeInController


def test_barge_in_disabled_never_triggers(unique_id: str) -> None:
    controller = BargeInController(enabled=False)
    result = controller.is_barge_in(
        vad_speech_seconds=2.0,
        stt_preview_text="стоп",
        tts_is_active=True,
    )
    assert result is False


def test_barge_in_not_triggered_when_tts_not_active(unique_id: str) -> None:
    controller = BargeInController(enabled=True)
    result = controller.is_barge_in(
        vad_speech_seconds=2.0,
        stt_preview_text="стоп",
        tts_is_active=False,
    )
    assert result is False


def test_barge_in_not_triggered_on_short_vad(unique_id: str) -> None:
    controller = BargeInController(enabled=True)
    result = controller.is_barge_in(
        vad_speech_seconds=0.1,
        stt_preview_text="стоп",
        tts_is_active=True,
    )
    assert result is False


def test_barge_in_triggered_by_command_word(unique_id: str) -> None:
    controller = BargeInController(
        enabled=True,
        command_words=["стоп", "хватит"],
    )
    result = controller.is_barge_in(
        vad_speech_seconds=0.5,
        stt_preview_text="пожалуйста стоп",
        tts_is_active=True,
    )
    assert result is True


def test_barge_in_triggered_by_long_speech(unique_id: str) -> None:
    controller = BargeInController(
        enabled=True,
        smart_turn_buffer_ms=200,
        command_words=[],
    )
    result = controller.is_barge_in(
        vad_speech_seconds=0.5,
        stt_preview_text="какой-то нейтральный текст без команд",
        tts_is_active=True,
    )
    assert result is True


def test_barge_in_respects_cooldown(unique_id: str) -> None:
    controller = BargeInController(
        enabled=True,
        cooldown_ms=5000,
        command_words=["стоп"],
    )
    controller._last_barge_in_ts = time.monotonic()

    result = controller.is_barge_in(
        vad_speech_seconds=1.0,
        stt_preview_text="стоп",
        tts_is_active=True,
    )
    assert result is False


async def test_barge_in_execute_marks_tts_inactive(unique_id: str) -> None:
    controller = BargeInController(enabled=True)
    session = MagicMock()
    session.session_id = f"sess-{unique_id}"
    session.mark_tts_active = MagicMock()

    await controller.execute_barge_in(session)

    session.mark_tts_active.assert_called_once_with(False)


async def test_barge_in_execute_updates_timestamp(unique_id: str) -> None:
    controller = BargeInController(enabled=True)
    session = MagicMock()
    session.session_id = f"sess-{unique_id}"

    before = time.monotonic()
    await controller.execute_barge_in(session)
    after = time.monotonic()

    assert before <= controller._last_barge_in_ts <= after
