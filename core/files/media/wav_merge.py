"""Склейка нескольких WAV (PCM s16le mono) в один файл.

Потоковый TTS отдаёт по одному полному WAV на каждый текстовый чанк. Конкатенация
сырых байт ``wav1 + wav2 + …`` не является одним медиафайлом: браузерный
``<audio>`` и большинство декодеров воспроизводят только первый RIFF.
"""

from __future__ import annotations

import io
import wave

from core.files.media.pcm_to_wav import pcm_s16le_mono_to_wav


def merge_wav_s16le_mono_files(wav_chunks: list[bytes]) -> bytes:
    if not wav_chunks:
        raise ValueError("merge_wav_s16le_mono_files: wav_chunks is empty.")
    pcm_parts: list[bytes] = []
    sample_rate: int | None = None
    for idx, blob in enumerate(wav_chunks):
        if len(blob) < 12 or blob[:4] != b"RIFF" or blob[8:12] != b"WAVE":
            raise ValueError(
                f"merge_wav_s16le_mono_files: chunk {idx} is not RIFF/WAV."
            )
        with wave.open(io.BytesIO(blob), "rb") as w:
            channels = w.getnchannels()
            sampwidth = w.getsampwidth()
            framerate = w.getframerate()
            if channels != 1:
                raise ValueError(
                    f"merge_wav_s16le_mono_files: expected mono, chunk {idx} channels={channels}."
                )
            if sampwidth != 2:
                raise ValueError(
                    f"merge_wav_s16le_mono_files: expected s16le, chunk {idx} sampwidth={sampwidth}."
                )
            if sample_rate is None:
                sample_rate = framerate
            elif framerate != sample_rate:
                raise ValueError(
                    f"merge_wav_s16le_mono_files: sample_rate {sample_rate} != {framerate} in chunk {idx}."
                )
            frames = w.readframes(w.getnframes())
        if frames:
            pcm_parts.append(frames)
    if sample_rate is None:
        raise ValueError("merge_wav_s16le_mono_files: failed to determine sample_rate.")
    merged_pcm = b"".join(pcm_parts)
    if not merged_pcm:
        raise ValueError("merge_wav_s16le_mono_files: PCM is empty after parsing WAV.")
    return pcm_s16le_mono_to_wav(merged_pcm, sample_rate=sample_rate)


__all__ = ["merge_wav_s16le_mono_files"]
