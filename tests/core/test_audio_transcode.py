"""Тесты перекодирования голосовых под iOS (AAC M4A)."""

import shutil

import pytest

from core.files.audio_transcode import (
    audio_needs_ios_compatible_transcode,
    resolve_ios_transcode_source,
    sniff_ios_incompatible_audio_magic,
    transcode_audio_bytes_to_m4a_aac,
)


@pytest.mark.parametrize(
    "ct,expected",
    [
        ("audio/webm", True),
        ("audio/webm;codecs=opus", True),
        ("audio/ogg", True),
        ("application/ogg", True),
        ("audio/mp4", False),
        ("audio/mpeg", False),
        ("video/webm", True),
        ("audio/flac", True),
        ("", False),
    ],
)
def test_audio_needs_ios_compatible_transcode(ct: str, expected: bool) -> None:
    assert audio_needs_ios_compatible_transcode(ct) is expected


def test_sniff_webm_magic() -> None:
    assert sniff_ios_incompatible_audio_magic(b"\x1a\x45\xdf\xa3") == ".webm"
    assert sniff_ios_incompatible_audio_magic(b"OggS\x00") == ".ogg"
    assert sniff_ios_incompatible_audio_magic(b"xxxx") is None


def test_resolve_octet_stream_webm_sniff() -> None:
    webm_head = b"\x1a\x45\xdf\xa3" + b"\x00" * 40
    need, suf = resolve_ios_transcode_source(
        "application/octet-stream",
        "upload.bin",
        webm_head,
    )
    assert need is True
    assert suf == ".webm"


def test_resolve_skips_plain_bytes() -> None:
    need, _suf = resolve_ios_transcode_source(
        "application/octet-stream",
        "doc.pdf",
        b"%PDF-1.4",
    )
    assert need is False


@pytest.mark.asyncio
async def test_transcode_produces_m4a_when_ffmpeg_and_webm() -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg не установлен")

    import subprocess
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        webm_path = Path(td) / "s.webm"
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=mono",
                "-t",
                "0.15",
                "-c:a",
                "libopus",
                str(webm_path),
            ],
            check=True,
            capture_output=True,
        )
        webm_bytes = webm_path.read_bytes()
        assert len(webm_bytes) > 0

    m4a = await transcode_audio_bytes_to_m4a_aac(webm_bytes, ".webm")
    assert len(m4a) > 100
    assert m4a[4:8] == b"ftyp" or m4a[0:4] == b"\x00\x00\x00\x20"
