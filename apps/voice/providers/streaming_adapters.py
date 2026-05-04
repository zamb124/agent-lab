"""Универсальные streaming-адаптеры для STT/TTS/VAD voice сессии.

Эти адаптеры — единственный способ оборачивать batch-клиента из
`core.clients.{stt,tts,vad}_client` в streaming-интерфейс
`apps.voice.providers.base.{BaseSTTProvider,BaseTTSProvider,BaseVADProvider}`.

Не привязаны к провайдеру: внутрь передаётся уже резолвнутый клиент
(`BaseSTTClient` / `BaseTTSClient` / `BaseVADClient`), полученный через
`core.clients.voice_resolver.get_*_client(*, company_id, override)`.
Сами провайдеры — `litserve` (provider-litserve), `cloud_ru`, `yandex`,
`sber` для STT/TTS, `litserve`/`silero_local` для VAD — об этом не знают.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from apps.voice.providers.base import (
    BaseSTTProvider,
    BaseTTSProvider,
    BaseVADProvider,
)
from core.clients.stt_client import BaseSTTClient, STTTranscriptionResult
from core.clients.tts_client import BaseTTSClient
from core.clients.vad_client import BaseVADClient
from core.files.media.pcm_to_wav import pcm_s16le_mono_to_wav
from core.logging import get_logger


logger = get_logger(__name__)


_FRAME_DURATION_S = 0.02


class StreamingSTTProvider(BaseSTTProvider):
    """Streaming STT через любой `BaseSTTClient`.

    Аккумулирует PCM-фреймы в буфере (`push_audio`); при `flush_buffer`
    упаковывает накопленное в WAV (mono s16le) и отправляет в batch-клиент.
    Сырой `audio/pcm` без заголовков Cloud.ru Whisper и ряд других эндпоинтов не принимают (`Format not recognised`).
    """

    def __init__(
        self,
        *,
        stt_client: BaseSTTClient,
        sample_rate: int = 16000,
        language: Optional[str] = None,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError("StreamingSTTProvider: sample_rate должен быть > 0.")
        self._stt_client = stt_client
        self._sample_rate = sample_rate
        self._language = language
        self._audio_buffer: bytearray = bytearray()

    async def init(self, config: Optional[Any] = None) -> None:
        return None

    async def push_audio(self, chunk: bytes) -> None:
        if not chunk:
            return
        self._audio_buffer.extend(chunk)

    async def flush_buffer(self) -> Optional[STTTranscriptionResult]:
        if not self._audio_buffer:
            return None
        pcm = bytes(self._audio_buffer)
        self._audio_buffer = bytearray()
        wav = pcm_s16le_mono_to_wav(pcm, sample_rate=self._sample_rate)
        return await self._stt_client.transcribe_audio(
            audio_bytes=wav,
            file_name="voice_segment.wav",
            mime_type="audio/wav",
            language=self._language,
        )

    async def peek_transcript(
        self, *, min_buffer_bytes: int = 16000
    ) -> Optional[STTTranscriptionResult]:
        """Прочитать текущий буфер без его сброса (chunked-batch partial).

        Используется `stt_worker` для периодической отправки промежуточных
        транскриптов (`final=False`) во время открытого VAD-окна. В отличие
        от ``flush_buffer`` буфер не очищается — продолжаем накапливать тот
        же самый сегмент, и финальный ``flush_buffer`` после паузы вернёт
        полный текст.

        ``min_buffer_bytes`` по умолчанию = 16000 байт = 0.5 s @ 16 kHz s16le mono.
        Если PCM меньше — возвращает ``None`` (батч-провайдеры на коротких
        фрагментах часто отдают пустую строку).
        """
        if min_buffer_bytes <= 0:
            raise ValueError(
                "StreamingSTTProvider.peek_transcript: min_buffer_bytes должен быть > 0"
            )
        if len(self._audio_buffer) < min_buffer_bytes:
            return None
        pcm = bytes(self._audio_buffer)
        wav = pcm_s16le_mono_to_wav(pcm, sample_rate=self._sample_rate)
        return await self._stt_client.transcribe_audio(
            audio_bytes=wav,
            file_name="voice_segment_partial.wav",
            mime_type="audio/wav",
            language=self._language,
        )

    def reset(self) -> None:
        self._audio_buffer = bytearray()

    def has_buffered_audio(self) -> bool:
        return len(self._audio_buffer) > 0


class StreamingTTSProvider(BaseTTSProvider):
    """Streaming TTS через любой `BaseTTSClient`.

    `synthesize(text)` вызывает batch `tts_client.synthesize(...)` и
    возвращает сырые audio bytes; формат / голос / sample_rate уже
    зафиксированы в batch-клиенте при создании через resolver.
    """

    def __init__(self, *, tts_client: BaseTTSClient) -> None:
        self._tts_client = tts_client
        self._initialized = False

    async def init(self, config: Optional[Any] = None) -> None:
        self._initialized = True

    async def synthesize(self, text: str) -> bytes:
        if not self._initialized:
            raise RuntimeError("StreamingTTSProvider не инициализирован (вызовите init).")
        if text == "":
            raise ValueError("StreamingTTSProvider: пустой text.")
        result = await self._tts_client.synthesize(text=text)
        return result.audio_bytes

    async def close(self) -> None:
        self._initialized = False


class StreamingVADProvider(BaseVADProvider):
    """Streaming VAD по канону LiveKit/Pipecat поверх ``BaseVADClient``.

    Архитектура (`https://docs.livekit.io/agents/build/turns/vad`):

    1. Клиент шлёт PCM произвольной длины (типично 20 ms = 320 сэмплов на
       16 kHz). Провайдер копит во внутреннем буфере и режет на
       **фиксированные** chunks ровно по 512 сэмплов на 16 kHz / 256 на
       8 kHz — silero-vad v5 принимает только такие размеры
       (`https://github.com/snakers4/silero-vad/wiki/FAQ`).
    2. На каждом 32 ms-чанке вызывается ``vad_client.detect_speech_prob``
       — **без** сброса state модели между вызовами; state хранит
       контекст голосовой сессии, без которого короткие чанки неотличимы
       от шума.
    3. Решение state (`SILENCE` ↔ `SPEECH`) обновляется через гистерезис
       и сглаживание длительности:
       * SILENCE → SPEECH: prob ≥ ``activation_threshold`` непрерывно
         в течение ``min_speech_ms`` (защита от ложных стартов на
         щелчках).
       * SPEECH → SILENCE: prob < ``deactivation_threshold`` непрерывно
         в течение ``min_silence_ms`` (граница конца фразы).
    4. Pre-roll buffer ``prefix_padding_ms`` — rolling-окно последних N мс
       PCM. При переходе SILENCE → SPEECH ``stt_worker`` вызывает
       ``consume_preroll()`` и пушит pre-roll в STT, чтобы не потерять
       первый звук слова.

    Не-streaming клиент (`supports_streaming=False`) не поддерживается:
    real-time VAD без per-chunk вероятности невозможен. Платформенный
    деплоймент-default — `silero_local`; `mock` для тестов; для litserve
    нужен per-frame `/v1/audio/vad/prob` endpoint (TODO провайдер).
    """

    def __init__(
        self,
        *,
        vad_client: BaseVADClient,
        sample_rate: int = 16000,
        activation_threshold: float = 0.5,
        deactivation_threshold: float = 0.35,
        min_speech_ms: int = 50,
        min_silence_ms: int = 550,
        prefix_padding_ms: int = 500,
    ) -> None:
        if sample_rate not in (8000, 16000):
            raise ValueError(
                "StreamingVADProvider: sample_rate должен быть 8000 или 16000."
            )
        if not vad_client.supports_streaming:
            raise ValueError(
                f"StreamingVADProvider: vad_client {type(vad_client).__name__} "
                "не поддерживает streaming (supports_streaming=False); используйте "
                "silero_local или mock."
            )
        if not 0.0 <= activation_threshold <= 1.0:
            raise ValueError("activation_threshold должен быть в [0.0, 1.0].")
        if not 0.0 <= deactivation_threshold <= 1.0:
            raise ValueError("deactivation_threshold должен быть в [0.0, 1.0].")
        if deactivation_threshold > activation_threshold:
            raise ValueError(
                "deactivation_threshold должен быть ≤ activation_threshold "
                "(гистерезис)."
            )
        if min_speech_ms < 0:
            raise ValueError("min_speech_ms должен быть ≥ 0.")
        if min_silence_ms < 0:
            raise ValueError("min_silence_ms должен быть ≥ 0.")
        if prefix_padding_ms < 0:
            raise ValueError("prefix_padding_ms должен быть ≥ 0.")

        self._vad_client = vad_client
        self._sample_rate = sample_rate
        self._activation_threshold = activation_threshold
        self._deactivation_threshold = deactivation_threshold
        self._min_speech_ms = min_speech_ms
        self._min_silence_ms = min_silence_ms

        self._chunk_samples = 512 if sample_rate == 16000 else 256
        self._chunk_bytes = self._chunk_samples * 2
        self._chunk_duration_ms = self._chunk_samples * 1000 // sample_rate

        self._preroll_max_bytes = sample_rate * 2 * prefix_padding_ms // 1000

        self._chunk_buffer: bytearray = bytearray()
        self._preroll_buffer: bytearray = bytearray()
        self._lock = asyncio.Lock()

        self._state: str = "silence"
        self._pending_speech_ms: int = 0
        self._pending_silence_ms: int = 0

    async def detect_speech(self, audio_pcm: bytes, sample_rate: int) -> bool:
        if sample_rate != self._sample_rate:
            raise ValueError(
                f"StreamingVADProvider: ожидается sample_rate={self._sample_rate}, "
                f"получено {sample_rate}."
            )

        async with self._lock:
            self._preroll_buffer.extend(audio_pcm)
            if len(self._preroll_buffer) > self._preroll_max_bytes:
                excess = len(self._preroll_buffer) - self._preroll_max_bytes
                del self._preroll_buffer[:excess]

            self._chunk_buffer.extend(audio_pcm)
            while len(self._chunk_buffer) >= self._chunk_bytes:
                chunk = bytes(self._chunk_buffer[: self._chunk_bytes])
                del self._chunk_buffer[: self._chunk_bytes]
                prob = await self._vad_client.detect_speech_prob(
                    audio_bytes=chunk,
                    sample_rate=self._sample_rate,
                )
                self._update_state(prob)

            return self._state == "speech"

    def _update_state(self, prob: float) -> None:
        if self._state == "silence":
            if prob >= self._activation_threshold:
                self._pending_speech_ms += self._chunk_duration_ms
                self._pending_silence_ms = 0
                if self._pending_speech_ms >= self._min_speech_ms:
                    self._state = "speech"
                    self._pending_speech_ms = 0
            else:
                self._pending_speech_ms = 0
            return

        if prob < self._deactivation_threshold:
            self._pending_silence_ms += self._chunk_duration_ms
            self._pending_speech_ms = 0
            if self._pending_silence_ms >= self._min_silence_ms:
                self._state = "silence"
                self._pending_silence_ms = 0
        else:
            self._pending_silence_ms = 0

    def consume_preroll(self) -> bytes:
        """Забрать накопленный pre-roll PCM (rolling последние ``prefix_padding_ms``).

        Используется ``stt_worker`` ровно один раз на переходе
        SILENCE → SPEECH: то, что лежало в rolling-буфере до старта VAD,
        пушим в ``stt_provider.push_audio`` перед текущим фреймом.
        """
        out = bytes(self._preroll_buffer)
        self._preroll_buffer = bytearray()
        return out

    @property
    def state(self) -> str:
        return self._state

    def reset_state(self) -> None:
        self._chunk_buffer = bytearray()
        self._preroll_buffer = bytearray()
        self._state = "silence"
        self._pending_speech_ms = 0
        self._pending_silence_ms = 0
        reset_streaming = getattr(self._vad_client, "reset_streaming_state", None)
        if callable(reset_streaming):
            reset_streaming()


__all__ = [
    "StreamingSTTProvider",
    "StreamingTTSProvider",
    "StreamingVADProvider",
]
