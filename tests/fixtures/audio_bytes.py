"""Минимальный валидный PCM WAV (тишина) для тестов загрузки файлов и STT.

Один источник правды: без дублирования в e2e по сервисам.
"""

from __future__ import annotations

import io
import struct


def minimal_wav_silence(
    duration_sec: float = 1.0,
    sample_rate: int = 16000,
    bits_per_sample: int = 16,
) -> bytes:
    num_channels = 1
    num_samples = int(sample_rate * duration_sec)
    if num_samples < 1:
        num_samples = 1
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = num_samples * block_align

    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))
    buf.write(struct.pack("<H", 1))
    buf.write(struct.pack("<H", num_channels))
    buf.write(struct.pack("<I", sample_rate))
    buf.write(struct.pack("<I", byte_rate))
    buf.write(struct.pack("<H", block_align))
    buf.write(struct.pack("<H", bits_per_sample))
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    buf.write(b"\x00" * data_size)
    return buf.getvalue()
