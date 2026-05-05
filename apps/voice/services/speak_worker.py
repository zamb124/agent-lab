"""Speak worker — потоковое озвучивание текста, приходящего в voice session.

Универсальный компонент: не знает про ``apps/flows``, A2A, agent-logic. Кормит
``session.synthesis_queue`` текстовыми чанками, прогоняет их через
``core.clients.voice_chunker.VoiceChunker`` и потоковый TTS
(``voice_resolver.get_tts_streamer``), отправляет PCM в ``VoiceClientChannel``
без ожидания полного ответа.

Источник текста — **любой**:

* клиентский bridge (веб/моб.) перегоняет токены ответа агента из A2A-стрима
  в текстовые JSON-команды ``{"type":"speak","text":...}`` на том же WS;
* тестовый вызов прямо в voice;
* будущие интеграции (TaskIQ push, batch-сериал и т. д.).

Контракт очереди ``session.synthesis_queue``:

* любой непустой ``str`` (кроме ``_END_OF_UTTERANCE``) — добавить в
  ``VoiceChunker``, синтезировать готовые речевые куски и отправить PCM;
* ``_END_OF_UTTERANCE`` — завершить текущее высказывание: flush чанкера,
  синтезировать остаток, сбросить состояние для следующего.

Правило «ни миллисекунды»: первый PCM-чанк уходит клиенту сразу после первой
синтаксической границы, а не после прихода всего текста.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from apps.voice.services.voice_client_channel import VoiceClientChannel
from apps.voice.services.voice_session import VoiceSession
from core.clients.tts_streaming import BaseTTSStreamer
from core.clients.voice_chunker import VoiceChunker
from core.logging import get_logger


logger = get_logger(__name__)

_END_OF_UTTERANCE: str = "__EOU__"
"""Сентинел в ``synthesis_queue``, означающий «конец фразы — флашить чанкер»."""


async def run_speak_worker(
    session: VoiceSession,
    tts_streamer: BaseTTSStreamer,
    *,
    channel: VoiceClientChannel,
    chunker: Optional[VoiceChunker] = None,
) -> None:
    """Читать ``synthesis_queue`` и отправлять клиенту PCM через ``channel``.

    Кроме аудио — публикует события ``tts_state`` (``playing`` / ``stopped``),
    чтобы клиент мог согласованно показывать состояние и детектировать
    barge-in на своей стороне.
    """
    chunker = chunker or VoiceChunker()

    while session.active:
        try:
            text_piece = await session.synthesis_queue.get()
        except asyncio.CancelledError:
            raise

        if text_piece == _END_OF_UTTERANCE:
            await _flush_and_synthesize(
                session=session,
                tts_streamer=tts_streamer,
                chunker=chunker,
                channel=channel,
            )
            continue

        if not isinstance(text_piece, str) or text_piece == "":
            continue

        await _announce_tts_started(session=session, channel=channel)
        try:
            for speakable in chunker.feed(text_piece):
                if not session.active:
                    break
                audio_bytes = await tts_streamer.synthesize_chunk(speakable)
                if audio_bytes:
                    await channel.send_pcm(audio_bytes)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(
                "voice.speak_worker.synthesis_failed",
                session_id=session.session_id,
            )
            await channel.send_error(
                code="voice/speak/synthesis_failed",
                detail=str(exc),
            )


async def _flush_and_synthesize(
    *,
    session: VoiceSession,
    tts_streamer: BaseTTSStreamer,
    chunker: VoiceChunker,
    channel: VoiceClientChannel,
) -> None:
    """Флашим остаток и отправляем синтез по сегментам (лимит чанкера)."""
    tails = chunker.flush()
    if not tails:
        await _announce_tts_stopped(session=session, channel=channel)
        return

    try:
        for tail in tails:
            audio_bytes = await tts_streamer.synthesize_chunk(tail)
            if audio_bytes:
                await channel.send_pcm(audio_bytes)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception(
            "voice.speak_worker.flush_failed",
            session_id=session.session_id,
        )
        await channel.send_error(
            code="voice/speak/flush_failed",
            detail=str(exc),
        )
    finally:
        await _announce_tts_stopped(session=session, channel=channel)


async def _announce_tts_started(
    *, session: VoiceSession, channel: VoiceClientChannel
) -> None:
    if session.is_tts_active:
        return
    session.mark_tts_active(True)
    await channel.send_tts_state("playing")


async def _announce_tts_stopped(
    *, session: VoiceSession, channel: VoiceClientChannel
) -> None:
    if not session.is_tts_active:
        return
    session.mark_tts_active(False)
    await channel.send_tts_state("stopped")


async def enqueue_speak(session: VoiceSession, text: str) -> None:
    """Публичный helper: положить текст в ``synthesis_queue``."""
    if text == "":
        return
    await session.synthesis_queue.put(text)


async def enqueue_end_of_utterance(session: VoiceSession) -> None:
    """Публичный helper: завершить текущее высказывание (flush чанкера)."""
    await session.synthesis_queue.put(_END_OF_UTTERANCE)


async def clear_pending_synthesis(session: VoiceSession) -> int:
    """Barge-in помощник: очистить очереди синтеза и исходящего аудио.

    Возвращает число удалённых элементов (чистый счётчик для логов).
    """
    return session.clear_synthesis_and_audio_out()


__all__ = [
    "run_speak_worker",
    "enqueue_speak",
    "enqueue_end_of_utterance",
    "clear_pending_synthesis",
    "_END_OF_UTTERANCE",
]
