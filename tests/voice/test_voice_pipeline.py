"""Интеграционные тесты голосового пайплайна.

Тестирует реальную цепочку: VoiceSession + VAD + STT + TTS + Chunker + Workers.
Внешние ML-модели заменены тестовыми реализациями (не mock.patch).

VAD использует always_speech=False, что детектирует речь по ненулевым байтам:
  - speech_frame = b'\\x01\\x00' * N  → VAD=True
  - silence_frame = b'\\x00\\x00' * N → VAD=False
"""

import asyncio

import pytest

from apps.voice.providers.stt.mock import MockSTTProvider
from apps.voice.providers.tts.mock import MockTTSProvider
from apps.voice.providers.vad.mock import MockVADProvider
from apps.voice.services.voice_barge_in import BargeInController
from apps.voice.services.voice_chunker import VoiceChunker
from apps.voice.services.voice_session import VoiceSession
from apps.voice.workers.stt_worker import run_stt_worker
from apps.voice.workers.tts_worker import run_tts_worker

SPEECH_FRAME = b"\x01\x00" * 320   # ненулевые байты → VAD=True
SILENCE_FRAME = b"\x00\x00" * 320  # нулевые байты → VAD=False
SILENCE_THRESHOLD = 10              # количество тихих фреймов для flush


async def _feed_utterance(session: VoiceSession, *, speech_count: int = 3) -> None:
    """Подать речевые фреймы, затем тишину для триггера flush."""
    for _ in range(speech_count):
        await session.audio_in_queue.put(SPEECH_FRAME)
    for _ in range(SILENCE_THRESHOLD):
        await session.audio_in_queue.put(SILENCE_FRAME)


# ---------------------------------------------------------------------------
# STT pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_stt_worker_produces_transcription(unique_id: str) -> None:
    """STT worker распознаёт речь и вызывает callback с текстом."""
    session = VoiceSession(session_id=f"sess-{unique_id}")
    # always_speech=False: детекция по ненулевым байтам (реалистичнее)
    vad = MockVADProvider(always_speech=False)
    stt = MockSTTProvider(text="привет мир")

    done = asyncio.Event()
    transcribed: list[str] = []

    async def on_transcription(sess: VoiceSession, text: str) -> None:
        transcribed.append(text)
        done.set()

    worker_task = asyncio.create_task(
        run_stt_worker(session, vad, stt, on_full_transcription=on_transcription)
    )

    await _feed_utterance(session)

    # Ждём события транскрипции
    await asyncio.wait_for(done.wait(), timeout=5.0)

    worker_task.cancel()
    await asyncio.gather(worker_task, return_exceptions=True)

    assert transcribed == ["привет мир"]
    assert stt.call_count == 1


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_stt_worker_no_transcription_on_silence_only(unique_id: str) -> None:
    """STT worker не выдаёт транскрипцию если нет речевых фреймов."""
    session = VoiceSession(session_id=f"sess-{unique_id}")
    vad = MockVADProvider(always_speech=False)  # нулевые байты → False
    stt = MockSTTProvider(text="не должно быть")

    transcribed: list[str] = []

    async def on_transcription(sess: VoiceSession, text: str) -> None:
        transcribed.append(text)

    worker_task = asyncio.create_task(
        run_stt_worker(session, vad, stt, on_full_transcription=on_transcription)
    )

    # Только тишина
    for _ in range(20):
        await session.audio_in_queue.put(SILENCE_FRAME)

    await asyncio.sleep(0.1)
    worker_task.cancel()
    await asyncio.gather(worker_task, return_exceptions=True)

    assert transcribed == []
    assert stt.call_count == 0


@pytest.mark.asyncio
@pytest.mark.timeout(15)
async def test_stt_worker_multiple_utterances(unique_id: str) -> None:
    """STT worker обрабатывает несколько фраз подряд."""
    session = VoiceSession(session_id=f"sess-{unique_id}")
    vad = MockVADProvider(always_speech=False)
    stt = MockSTTProvider(text="слово")

    utterances: list[str] = []
    done = asyncio.Event()

    async def on_transcription(sess: VoiceSession, text: str) -> None:
        utterances.append(text)
        if len(utterances) >= 2:
            done.set()

    worker_task = asyncio.create_task(
        run_stt_worker(session, vad, stt, on_full_transcription=on_transcription)
    )

    await _feed_utterance(session)
    await _feed_utterance(session)

    await asyncio.wait_for(done.wait(), timeout=10.0)

    worker_task.cancel()
    await asyncio.gather(worker_task, return_exceptions=True)

    assert len(utterances) == 2
    assert stt.call_count == 2


# ---------------------------------------------------------------------------
# TTS pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_tts_worker_synthesizes_text(unique_id: str) -> None:
    """TTS worker синтезирует текст и кладёт аудио в очередь."""
    session = VoiceSession(session_id=f"sess-{unique_id}")
    tts = MockTTSProvider()
    chunker = VoiceChunker()

    worker_task = asyncio.create_task(run_tts_worker(session, tts, chunker))

    await session.text_in_queue.put("Привет мир. Как дела?")

    # Даём время на обработку
    await asyncio.sleep(0.2)

    worker_task.cancel()
    await asyncio.gather(worker_task, return_exceptions=True)

    assert len(tts.synthesized_texts) > 0


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_tts_worker_marks_tts_active(unique_id: str) -> None:
    """TTS worker сбрасывает флаг tts_active после завершения синтеза."""
    session = VoiceSession(session_id=f"sess-{unique_id}")
    tts = MockTTSProvider()
    chunker = VoiceChunker()

    assert not session.tts_active

    worker_task = asyncio.create_task(run_tts_worker(session, tts, chunker))

    await session.text_in_queue.put("Тест синтеза.")

    # Ждём пока воркер обработает текст
    await asyncio.sleep(0.2)

    worker_task.cancel()
    await asyncio.gather(worker_task, return_exceptions=True)

    # После отмены флаг должен быть False (finally в worker сбрасывает)
    assert not session.tts_active


# ---------------------------------------------------------------------------
# Полная цепочка STT → TTS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.timeout(15)
async def test_full_pipeline_stt_to_tts(unique_id: str) -> None:
    """Интеграция STT → callback → TTS: речь приводит к синтезу ответа."""
    session = VoiceSession(session_id=f"sess-{unique_id}")
    vad = MockVADProvider(always_speech=False)
    stt = MockSTTProvider(text="расскажи анекдот")
    tts = MockTTSProvider()
    chunker = VoiceChunker()

    done = asyncio.Event()

    async def on_transcription(sess: VoiceSession, text: str) -> None:
        response = f"Ответ на: {text}"
        await sess.text_in_queue.put(response)
        # Небольшая пауза чтобы TTS успел обработать
        await asyncio.sleep(0.1)
        done.set()

    stt_task = asyncio.create_task(
        run_stt_worker(session, vad, stt, on_full_transcription=on_transcription)
    )
    tts_task = asyncio.create_task(run_tts_worker(session, tts, chunker))

    await _feed_utterance(session)

    await asyncio.wait_for(done.wait(), timeout=10.0)

    stt_task.cancel()
    tts_task.cancel()
    await asyncio.gather(stt_task, tts_task, return_exceptions=True)

    assert stt.call_count == 1
    assert len(tts.synthesized_texts) > 0
    assert any("расскажи анекдот" in t for t in tts.synthesized_texts)


# ---------------------------------------------------------------------------
# VoiceSession lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_voice_session_cancel_stops_workers(unique_id: str) -> None:
    """Отмена сессии прекращает работу всех воркеров."""
    session = VoiceSession(session_id=f"sess-{unique_id}")
    vad = MockVADProvider(always_speech=False)
    stt = MockSTTProvider(text="test")
    tts = MockTTSProvider()
    chunker = VoiceChunker()

    stt_task = asyncio.create_task(run_stt_worker(session, vad, stt))
    tts_task = asyncio.create_task(run_tts_worker(session, tts, chunker))
    session.add_task(stt_task)
    session.add_task(tts_task)

    assert session.active

    await session.cancel()

    # После cancel задачи должны завершиться
    await asyncio.wait_for(
        asyncio.gather(stt_task, tts_task, return_exceptions=True),
        timeout=3.0,
    )

    assert not session.active
    assert stt_task.done()
    assert tts_task.done()


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_voice_session_bytes_accounting(unique_id: str) -> None:
    """VoiceSession правильно считает принятые и отправленные байты."""
    session = VoiceSession(session_id=f"sess-{unique_id}")

    session.add_bytes_received(1024)
    session.add_bytes_received(512)
    session.add_bytes_sent(2048)

    assert session.bytes_received == 1536
    assert session.bytes_sent == 2048

    await session.cancel()


# ---------------------------------------------------------------------------
# Barge-in + VoiceChunker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_barge_in_cancels_tts_when_user_speaks(unique_id: str) -> None:
    """BargeIn сбрасывает TTS active при обнаружении речи пользователя."""
    session = VoiceSession(session_id=f"sess-{unique_id}")
    barge_in = BargeInController(enabled=True, smart_turn_buffer_ms=300)

    session.mark_tts_active(True)
    assert session.tts_active

    # Речь 0.6 секунды при активном TTS — должно сработать barge-in
    triggered = barge_in.is_barge_in(
        vad_speech_seconds=0.6,
        stt_preview_text="",
        tts_is_active=session.tts_active,
    )

    assert triggered

    await barge_in.execute_barge_in(session)
    assert not session.tts_active

    await session.cancel()


def test_voice_chunker_real_sentences_split() -> None:
    """VoiceChunker правильно режет связный текст на предложения."""
    chunker = VoiceChunker(min_words=2, chunk_max_chars=200)

    result = chunker.feed("Первое предложение завершено. Второе тоже. А вот третье длиннее всего.")
    remainder = chunker.flush()

    all_chunks = result + ([remainder] if remainder else [])
    assert len(all_chunks) >= 2
    joined = " ".join(all_chunks)
    assert "Первое предложение завершено" in joined
    assert "Второе тоже" in joined


def test_voice_chunker_flush_returns_remainder() -> None:
    """flush() возвращает накопленный хвост без завершающей пунктуации."""
    chunker = VoiceChunker(min_words=2)
    chunks = chunker.feed("Без точки в конце")
    assert chunks == []

    remainder = chunker.flush()
    assert remainder == "Без точки в конце"
