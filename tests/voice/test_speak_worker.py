"""Тесты speak_worker — потокового озвучивания voice-сессии.

speak_worker — универсальный воркер, не знающий про ``apps/flows``/A2A.
Кормит ``session.synthesis_queue`` текстом, прогоняет через ``VoiceChunker``
и потоковый TTS, отправляет PCM и ``tts_state`` через ``VoiceClientChannel``.

Проверяется:

* feed строк -> первый PCM уходит сразу после синтаксической границы;
* ``_END_OF_UTTERANCE`` -> flush чанкера и доотправка остатка;
* ``clear_pending_synthesis`` (barge-in) -> очистка обеих очередей;
* начало/конец озвучивания сопровождается ``tts_state`` фреймом.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest

from apps.voice.services.speak_worker import (
    _END_OF_UTTERANCE,
    clear_pending_synthesis,
    enqueue_end_of_utterance,
    enqueue_speak,
    run_speak_worker,
)
from apps.voice.services.voice_session import VoiceSession
from core.clients.tts_streaming import BaseTTSStreamer


class FakeTTSStreamer(BaseTTSStreamer):
    """Тестовый streamer: возвращает байты фиксированной длины на каждый кусок."""

    def __init__(self, *, bytes_per_call: int = 32) -> None:
        self._bytes_per_call = bytes_per_call
        self.calls: list[str] = []

    @property
    def provider(self) -> str:
        return "fake"

    @property
    def mime_type(self) -> str:
        return "audio/L16"

    @property
    def sample_rate(self) -> int:
        return 16000

    async def synthesize_chunk(self, text: str) -> bytes:
        self.calls.append(text)
        return bytes([0x11] * self._bytes_per_call)

    async def astream(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
        async for piece in text_stream:
            if piece:
                yield await self.synthesize_chunk(piece)


class FakeChannel:
    """Минимальный VoiceClientChannel-совместимый мок."""

    def __init__(self) -> None:
        self.pcm_frames: list[bytes] = []
        self.tts_states: list[str] = []
        self.errors: list[tuple[str, str]] = []

    async def send_pcm(self, audio_bytes: bytes) -> None:
        self.pcm_frames.append(audio_bytes)

    async def send_tts_state(self, state: str) -> None:
        self.tts_states.append(state)

    async def send_error(self, *, code: str, detail: str) -> None:
        self.errors.append((code, detail))


async def _drain(task: asyncio.Task[None], *, timeout: float = 2.0) -> None:
    try:
        await asyncio.wait_for(task, timeout=timeout)
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_speak_worker_emits_pcm_after_sentence_boundary(
    unique_id: str,
) -> None:
    session = VoiceSession(session_id=f"sess-{unique_id}")
    streamer = FakeTTSStreamer(bytes_per_call=16)
    channel = FakeChannel()

    worker = asyncio.create_task(run_speak_worker(session, streamer, channel=channel))

    await enqueue_speak(session, "Привет мир это тест.")
    await asyncio.sleep(0.05)

    await session.cancel()
    await _drain(worker)

    assert len(channel.pcm_frames) >= 1
    assert channel.tts_states[:1] == ["playing"]
    assert any("Привет" in text for text in streamer.calls)


@pytest.mark.asyncio
async def test_speak_worker_end_of_utterance_flushes_chunker(
    unique_id: str,
) -> None:
    session = VoiceSession(session_id=f"sess-{unique_id}")
    streamer = FakeTTSStreamer(bytes_per_call=8)
    channel = FakeChannel()

    worker = asyncio.create_task(run_speak_worker(session, streamer, channel=channel))

    await enqueue_speak(session, "Недописанная фраза без точки")
    await enqueue_end_of_utterance(session)
    await asyncio.sleep(0.05)

    await session.cancel()
    await _drain(worker)

    assert any(
        "Недописанная" in text for text in streamer.calls
    ), "Flush по _END_OF_UTTERANCE должен вызвать TTS на остатке буфера."
    assert "stopped" in channel.tts_states


@pytest.mark.asyncio
async def test_speak_worker_end_of_utterance_without_text_just_stops(
    unique_id: str,
) -> None:
    session = VoiceSession(session_id=f"sess-{unique_id}")
    streamer = FakeTTSStreamer()
    channel = FakeChannel()

    worker = asyncio.create_task(run_speak_worker(session, streamer, channel=channel))

    await enqueue_end_of_utterance(session)
    await asyncio.sleep(0.05)

    await session.cancel()
    await _drain(worker)

    assert streamer.calls == []
    assert channel.tts_states == []


@pytest.mark.asyncio
async def test_speak_worker_ignores_empty_and_non_str_payload(
    unique_id: str,
) -> None:
    session = VoiceSession(session_id=f"sess-{unique_id}")
    streamer = FakeTTSStreamer()
    channel = FakeChannel()

    worker = asyncio.create_task(run_speak_worker(session, streamer, channel=channel))

    await session.synthesis_queue.put("")
    await session.synthesis_queue.put(123)  # type: ignore[arg-type]
    await asyncio.sleep(0.05)

    await session.cancel()
    await _drain(worker)

    assert streamer.calls == []
    assert channel.pcm_frames == []


@pytest.mark.asyncio
async def test_clear_pending_synthesis_drains_queues(unique_id: str) -> None:
    session = VoiceSession(session_id=f"sess-{unique_id}")
    await session.synthesis_queue.put("скоро тебя отменят.")
    await session.audio_out_queue.put(b"\x00\x01")

    removed = await clear_pending_synthesis(session)

    assert removed >= 2
    assert session.synthesis_queue.empty()
    assert session.audio_out_queue.empty()


@pytest.mark.asyncio
async def test_speak_worker_end_of_utterance_sentinel_is_constant() -> None:
    assert _END_OF_UTTERANCE == "__EOU__"
