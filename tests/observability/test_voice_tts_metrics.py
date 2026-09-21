"""Runtime tests: voice TTS TTFA completion log."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import override

import pytest

from apps.voice.services.speak_worker import (
    enqueue_end_of_utterance,
    enqueue_speak,
    run_speak_worker,
)
from apps.voice.services.voice_session import VoiceSession
from core.clients.tts_streaming import BaseTTSStreamer
from core.context import Context, reset_context, set_context
from core.logging.attributes import LOG_TTS_PROVIDER, LOG_TTS_TTFA_MS
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from tests.fixtures.observability_log_capture import (
    find_caplog_record,
    require_log_fields,
    require_numeric_field,
)
from tests.observability.contracts import VOICE_TTS_RESPONSE

pytestmark = pytest.mark.timeout(30)


class _FakeTTSStreamer(BaseTTSStreamer):
    def __init__(self) -> None:
        self.calls: list[str] = []

    @property
    @override
    def provider(self) -> str:
        return "fake-tts"

    @property
    @override
    def content_type(self) -> str:
        return "audio/L16"

    @property
    @override
    def sample_rate(self) -> int:
        return 16000

    @override
    async def synthesize_chunk(self, text: str) -> bytes:
        self.calls.append(text)
        return bytes([0x11] * 32)

    @override
    async def astream(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
        async for piece in text_stream:
            if piece:
                yield await self.synthesize_chunk(piece)


class _FakeChannel:
    async def send_pcm(self, audio_bytes: bytes) -> None:
        _ = audio_bytes

    async def send_tts_state(self, state: str) -> None:
        _ = state

    async def send_error(self, *, code: str, detail: str) -> None:
        _ = code, detail


async def _spawn_speak_worker(
    session: VoiceSession,
    streamer: _FakeTTSStreamer,
    channel: _FakeChannel,
) -> asyncio.Task[None]:
    worker = asyncio.create_task(run_speak_worker(session, streamer, channel=channel))
    session.add_task(worker)
    return worker


async def _shutdown_speak_worker(
    session: VoiceSession,
    worker: asyncio.Task[None],
    *,
    timeout: float = 2.0,
) -> None:
    await session.cancel()
    try:
        await asyncio.wait_for(worker, timeout=timeout)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass


@pytest.mark.asyncio
async def test_voice_tts_response_includes_ttfa(
    observability_caplog: pytest.LogCaptureFixture,
    unique_id: str,
) -> None:
    token = set_context(
        Context(
            user=User(user_id=f"voice-obs-user-{unique_id}", name="voice-obs"),
            host="test",
            session_id=f"voice-obs:{unique_id}",
            channel="test",
            language=Language.RU,
            active_company=Company(
                company_id=f"voice-obs-co-{unique_id}",
                name="voice-obs",
                subdomain="voice-obs",
            ),
            user_companies=[],
            trace_id=unique_id,
            auth_token="voice-obs-token",
        )
    )
    session = VoiceSession(session_id=f"voice-obs-{unique_id}")
    streamer = _FakeTTSStreamer()
    channel = _FakeChannel()
    try:
        worker = await _spawn_speak_worker(session, streamer, channel)
        await enqueue_speak(session, "Привет мир это тест.")
        await asyncio.sleep(0.1)
        await enqueue_end_of_utterance(session)
        await asyncio.sleep(0.05)
        await _shutdown_speak_worker(session, worker)
    finally:
        reset_context(token)

    rec = find_caplog_record(
        observability_caplog,
        message=VOICE_TTS_RESPONSE.message,
        logger_name="core.clients.voice_logging",
    )
    fields = require_log_fields(
        rec,
        required={
            LOG_TTS_PROVIDER: str,
            LOG_TTS_TTFA_MS: (int, float),
        },
    )
    assert fields[LOG_TTS_PROVIDER] == "fake-tts"
    require_numeric_field(fields, LOG_TTS_TTFA_MS, min_value=0.0)
