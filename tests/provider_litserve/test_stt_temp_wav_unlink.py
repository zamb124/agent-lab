"""Временный wav STT удаляется после транскрипции; отсутствующий файл не роняет вызов."""

import os
import tempfile

from apps.provider_litserve.stt.engines import _unlink_temp_wav


def test_unlink_temp_wav_removes_file() -> None:
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    _unlink_temp_wav(path)
    assert os.path.exists(path) is False


def test_unlink_temp_wav_missing_file_returns() -> None:
    missing = os.path.join(tempfile.gettempdir(), "provider-litserve-missing-stt.wav")
    if os.path.exists(missing):
        os.unlink(missing)
    _unlink_temp_wav(missing)
