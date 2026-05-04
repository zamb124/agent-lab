"""Упаковка сырых PCM s16le mono в WAV для batch-STT (Whisper/OpenAI multipart)."""

from __future__ import annotations

import io
import wave


def pcm_s16le_mono_to_wav(pcm_bytes: bytes, *, sample_rate: int) -> bytes:
    if sample_rate <= 0:
        raise ValueError("pcm_s16le_mono_to_wav: sample_rate должен быть > 0.")
    if not pcm_bytes:
        raise ValueError("pcm_s16le_mono_to_wav: pcm_bytes не может быть пустым.")
    if len(pcm_bytes) % 2 != 0:
        raise ValueError(
            "pcm_s16le_mono_to_wav: ожидается целое число int16-сэмплов (чётная длина байт)."
        )
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm_bytes)
    return buf.getvalue()


__all__ = ["pcm_s16le_mono_to_wav"]
