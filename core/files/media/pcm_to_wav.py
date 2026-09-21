"""Упаковка сырых PCM s16le mono в WAV для batch-STT (Whisper/OpenAI multipart)."""

from __future__ import annotations

import io
import wave


def pcm_s16le_mono_to_wav(pcm_bytes: bytes, *, sample_rate: int) -> bytes:
    if sample_rate <= 0:
        raise ValueError("pcm_s16le_mono_to_wav: sample_rate must be > 0.")
    if not pcm_bytes:
        raise ValueError("pcm_s16le_mono_to_wav: pcm_bytes cannot be empty.")
    if len(pcm_bytes) % 2 != 0:
        raise ValueError(
            "pcm_s16le_mono_to_wav: expected a whole number of int16 samples (even byte length)."
        )
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm_bytes)
    return buf.getvalue()


__all__ = ["pcm_s16le_mono_to_wav"]
