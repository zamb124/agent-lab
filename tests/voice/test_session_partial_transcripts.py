"""Тесты partial transcripts в `stt_worker`.

При открытом VAD-окне воркер должен периодически дёргать `peek_transcript`
и слать `on_partial_transcription`. После паузы — финальный transcript через
`flush_buffer` + `on_final_transcription`.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import pytest

from apps.voice.providers.base import BaseSTTProvider
from apps.voice.providers.vad.mock import MockVADProvider
from apps.voice.services.voice_session import VoiceSession
from apps.voice.workers.stt_worker import run_stt_worker
from core.clients.stt_client import STTTranscriptionResult
from core.files.models import AudioTranscriptionStatus


SPEECH_FRAME = b"\x01\x00" * 320
SILENCE_FRAME = b"\x00\x00" * 320
_SILENCE_THRESHOLD = 10


class _PartialAwareSTT(BaseSTTProvider):
    """STT-стуб с поддержкой peek_transcript для теста chunked-batch."""

    def __init__(self, *, partial_text: str, final_text: str) -> None:
        self._buffer = bytearray()
        self._partial_text = partial_text
        self._final_text = final_text
        self.peek_calls: int = 0
        self.flush_calls: int = 0

    async def init(self, config: Optional[Any] = None) -> None:
        pass

    async def push_audio(self, chunk: bytes) -> None:
        self._buffer.extend(chunk)

    async def flush_buffer(self) -> Optional[STTTranscriptionResult]:
        self.flush_calls += 1
        if not self._buffer:
            return None
        self._buffer = bytearray()
        return STTTranscriptionResult(
            provider="mock",
            status=AudioTranscriptionStatus.DONE,
            text=self._final_text,
        )

    async def peek_transcript(
        self, *, min_buffer_bytes: int = 16000
    ) -> Optional[STTTranscriptionResult]:
        self.peek_calls += 1
        if len(self._buffer) < min_buffer_bytes:
            return None
        return STTTranscriptionResult(
            provider="mock",
            status=AudioTranscriptionStatus.DONE,
            text=self._partial_text,
        )

    def reset(self) -> None:
        self._buffer = bytearray()


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_stt_worker_emits_partial_then_final(unique_id: str) -> None:
    session = VoiceSession(session_id=f"sess-{unique_id}")
    vad = MockVADProvider(always_speech=False)
    stt = _PartialAwareSTT(
        partial_text=f"partial-{unique_id}",
        final_text=f"final-{unique_id}",
    )

    partials: list[str] = []
    final_done = asyncio.Event()
    finals: list[str] = []

    async def on_partial(_s: VoiceSession, text: str, _lang: str | None) -> None:
        partials.append(text)

    async def on_final(_s: VoiceSession, text: str, _lang: str | None) -> None:
        finals.append(text)
        final_done.set()

    worker_task = asyncio.create_task(
        run_stt_worker(
            session,
            vad,
            stt,
            on_final_transcription=on_final,
            on_partial_transcription=on_partial,
        )
    )

    for _ in range(60):
        await session.audio_in_queue.put(SPEECH_FRAME)
    for _ in range(_SILENCE_THRESHOLD):
        await session.audio_in_queue.put(SILENCE_FRAME)

    await asyncio.wait_for(final_done.wait(), timeout=5.0)

    worker_task.cancel()
    await asyncio.gather(worker_task, return_exceptions=True)

    assert finals == [f"final-{unique_id}"]
    assert len(partials) >= 1, f"ожидался >=1 partial, получено {partials}"
    assert all(p == f"partial-{unique_id}" for p in partials)


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_stt_worker_no_partial_when_disabled(
    unique_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`voice.stt.partial_transcripts_enabled=False` → partial-колбэк не вызывается."""
    from core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(
        settings.voice.stt, "partial_transcripts_enabled", False, raising=False
    )

    session = VoiceSession(session_id=f"sess-{unique_id}")
    vad = MockVADProvider(always_speech=False)
    stt = _PartialAwareSTT(partial_text="x", final_text="ok")

    partials: list[str] = []
    final_done = asyncio.Event()

    async def on_partial(_s: VoiceSession, text: str, _lang: str | None) -> None:
        partials.append(text)

    async def on_final(_s: VoiceSession, _t: str, _lang: str | None) -> None:
        final_done.set()

    worker_task = asyncio.create_task(
        run_stt_worker(
            session,
            vad,
            stt,
            on_final_transcription=on_final,
            on_partial_transcription=on_partial,
        )
    )

    for _ in range(60):
        await session.audio_in_queue.put(SPEECH_FRAME)
    for _ in range(_SILENCE_THRESHOLD):
        await session.audio_in_queue.put(SILENCE_FRAME)

    await asyncio.wait_for(final_done.wait(), timeout=5.0)
    worker_task.cancel()
    await asyncio.gather(worker_task, return_exceptions=True)

    assert partials == []
    assert stt.peek_calls == 0
