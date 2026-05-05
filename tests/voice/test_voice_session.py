"""Тесты VoiceSession и VoiceChunker."""

from __future__ import annotations

import asyncio

import pytest

from apps.voice.services.voice_chunker import VoiceChunker
from apps.voice.services.voice_session import VoiceSession


# === VoiceSession ===


def test_voice_session_created_with_correct_id(unique_id: str) -> None:
    session = VoiceSession(session_id=f"sess-{unique_id}")
    assert session.session_id == f"sess-{unique_id}"
    assert session.active is True
    assert session.is_tts_active is False
    assert session.bytes_sent == 0


def test_voice_session_queues_initialized(unique_id: str) -> None:
    session = VoiceSession(session_id=f"sess-{unique_id}")
    assert session.audio_in_queue.empty()
    assert session.audio_out_queue.empty()
    assert session.text_in_queue.empty()
    assert session.synthesis_queue.empty()


def test_voice_session_mark_tts_active(unique_id: str) -> None:
    session = VoiceSession(session_id=f"sess-{unique_id}")
    session.mark_tts_active(True)
    assert session.is_tts_active is True
    session.mark_tts_active(False)
    assert session.is_tts_active is False


def test_voice_session_record_bytes_sent(unique_id: str) -> None:
    session = VoiceSession(session_id=f"sess-{unique_id}")
    session.record_bytes_sent(100)
    session.record_bytes_sent(200)
    assert session.bytes_sent == 300


async def test_voice_session_cancel_stops_active(unique_id: str) -> None:
    session = VoiceSession(session_id=f"sess-{unique_id}")
    await session.cancel()
    assert session.active is False


async def test_voice_session_cancel_clears_queues(unique_id: str) -> None:
    session = VoiceSession(session_id=f"sess-{unique_id}")
    await session.audio_in_queue.put(b"frame1")
    await session.audio_out_queue.put(b"audio_out")
    await session.cancel()
    assert session.audio_in_queue.empty()
    assert session.audio_out_queue.empty()


async def test_voice_session_add_task_and_cancel(unique_id: str) -> None:
    session = VoiceSession(session_id=f"sess-{unique_id}")

    async def _dummy() -> None:
        await asyncio.sleep(10)

    task = asyncio.create_task(_dummy())
    session.add_task(task)
    await session.cancel()
    assert task.cancelled() or task.done()


# === VoiceChunker ===


def test_voice_chunker_splits_on_period() -> None:
    # "Раз два три." → 3 слова >= min_words=3 → первый чанк
    # "Четыре пять шесть." → 3 слова → второй чанк
    chunker = VoiceChunker()
    chunks = chunker.feed("Раз два три. Четыре пять шесть.")
    assert len(chunks) == 2
    assert chunks[0] == "Раз два три."
    assert chunks[1] == "Четыре пять шесть."


def test_voice_chunker_splits_on_question() -> None:
    chunker = VoiceChunker()
    chunks = chunker.feed("Ты умный робот? Я просто человек!")
    assert len(chunks) == 2


def test_voice_chunker_splits_on_exclamation() -> None:
    chunker = VoiceChunker()
    chunks = chunker.feed("Стоп стоп стоп! Хватит хватит хватит.")
    assert len(chunks) == 2


def test_voice_chunker_long_text_splits_by_comma() -> None:
    # Запятая в первых chunk_max_chars символах, текст длиннее лимита
    long_text = "слово слово слово, слово слово слово слово слово"
    chunker = VoiceChunker(chunk_max_chars=20)
    chunks = chunker.feed(long_text)
    assert len(chunks) >= 1
    assert "слово слово слово," in chunks[0]


def test_voice_chunker_flush_returns_remainder() -> None:
    chunker = VoiceChunker()
    chunker.feed("Текст без окончания")
    remainder = chunker.flush()
    assert remainder == ["Текст без окончания"]


def test_voice_chunker_flush_empty_after_complete_sentence() -> None:
    # 3 слова → чанк будет выдан в feed(), буфер пуст → flush() = []
    chunker = VoiceChunker()
    chunker.feed("Раз два три.")
    remainder = chunker.flush()
    assert remainder == []


def test_voice_chunker_accumulates_across_feeds() -> None:
    chunker = VoiceChunker()
    result1 = chunker.feed("Начало хорошего")
    result2 = chunker.feed(" предложения.")
    assert result1 == []
    assert len(result2) == 1
    assert "предложения." in result2[0]


def test_voice_chunker_flush_splits_long_tail_without_punctuation() -> None:
    chunker = VoiceChunker(chunk_max_chars=40, min_words=2)
    chunker.feed("один два " + "слово " * 30)
    parts = chunker.flush()
    assert len(parts) >= 3
    assert all(len(p) <= 40 for p in parts)
    joined = " ".join(parts)
    assert "один два" in joined
