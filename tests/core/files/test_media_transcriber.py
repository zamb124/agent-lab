"""Тесты MediaTranscriber и FileReader на реальных аудио/видео файлах.

STT работает через MockSTTClient (провайдер mock из конфигурации тестов),
но весь пайплайн — реальный: ffmpeg, чанкование, извлечение дорожки.

company_id для tier-резолва — синтетический с суффиксом ``unique_id``: у компании
``system`` в БД часто есть override ``company_voice_providers`` (litserve и т.д.),
он сильнее ``VOICE__STT__PROVIDER`` из окружения и даёт реальный HTTP без сервера.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from core.files.media.audio_extract import extract_audio_from_video
from core.files.media.chunked_stt import (
    audio_needs_mp3_upload_for_stt,
    is_stt_format_not_recognized_error,
    normalize_audio_to_mp3_for_stt,
    split_audio_for_stt_chunks,
    validate_stt_result_text,
)
from core.files.media.transcriber import MediaTranscriber, TranscriptionResult
from core.files.media.youtube import is_youtube_url
from core.files.reader import FileReader
from core.files.reader.models import FileReadKind
from tests.fixtures.audio_bytes import minimal_wav_silence


def _mock_stt_tier_company_id(unique_id: str) -> str:
    """Нет строки в ``company_voice_providers`` — STT из deployment (в тестах mock)."""
    return f"media_transcriber_tier_{unique_id}"


def _generate_test_mp4(duration_sec: float = 1.0) -> bytes:
    """Генерирует минимальный MP4 с видео (цветные полосы) и аудио (тишина) через ffmpeg."""
    with tempfile.TemporaryDirectory(prefix="test-mp4-") as work_dir:
        out_path = Path(work_dir) / "test.mp4"
        ffmpeg_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=duration={duration_sec}:size=160x120:rate=10",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=16000:cl=mono:d={duration_sec}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            "-shortest",
            str(out_path),
        ]
        result = subprocess.run(ffmpeg_cmd, check=False, capture_output=True, text=True)
        assert result.returncode == 0, f"ffmpeg не смог создать тестовый mp4: {result.stderr}"
        return out_path.read_bytes()


class TestExtractAudioFromVideo:
    def test_extracts_audio_from_valid_mp4(self) -> None:
        video_bytes = _generate_test_mp4(duration_sec=1.0)
        audio_bytes, audio_name = extract_audio_from_video(
            video_bytes=video_bytes, base_name="meeting.mp4"
        )
        assert len(audio_bytes) > 0
        assert audio_name == "meeting-audio.mp3"

    def test_raises_on_empty_bytes(self) -> None:
        with pytest.raises(ValueError, match="video_bytes"):
            extract_audio_from_video(video_bytes=b"", base_name="x.mp4")

    def test_raises_on_invalid_video(self) -> None:
        with pytest.raises(RuntimeError, match="Не удалось извлечь аудио"):
            extract_audio_from_video(video_bytes=b"\x00\x01\x02", base_name="corrupt.mp4")


class TestSplitAudioForSttChunks:
    def test_single_chunk_for_small_wav(self) -> None:
        wav = minimal_wav_silence(duration_sec=1.0)
        chunks = split_audio_for_stt_chunks(
            audio_bytes=wav,
            file_name="voice.wav",
            content_type="audio/wav",
            max_upload_bytes=50 * 1024 * 1024,
            chunk_duration_seconds=300,
            chunk_bitrate_kbps=32,
            chunk_sample_rate_hz=16000,
            chunk_channels=1,
        )
        assert len(chunks) >= 1
        for name, data, mime in chunks:
            assert name.endswith(".mp3")
            assert len(data) > 0
            assert mime == "audio/mpeg"

    def test_raises_on_empty_audio(self) -> None:
        with pytest.raises(ValueError, match="audio_bytes"):
            split_audio_for_stt_chunks(
                audio_bytes=b"",
                file_name="x.wav",
                content_type="audio/wav",
                max_upload_bytes=1024,
                chunk_duration_seconds=10,
                chunk_bitrate_kbps=32,
                chunk_sample_rate_hz=16000,
                chunk_channels=1,
            )


class TestValidateSttResultText:
    def test_valid_result(self) -> None:
        from core.clients.stt_client import STTTranscriptionResult
        from core.files.models import AudioTranscriptionStatus

        result = STTTranscriptionResult(
            provider="mock",
            status=AudioTranscriptionStatus.DONE,
            text="Привет мир",
        )
        text = validate_stt_result_text(
            transcript_result=result, job_id="test-1", context="unit"
        )
        assert text == "Привет мир"

    def test_raises_on_failed_status(self) -> None:
        from core.clients.stt_client import STTTranscriptionResult
        from core.files.models import AudioTranscriptionStatus

        result = STTTranscriptionResult(
            provider="mock",
            status=AudioTranscriptionStatus.FAILED,
            text="",
            error="timeout",
        )
        with pytest.raises(ValueError, match="неуспешный статус"):
            validate_stt_result_text(
                transcript_result=result, job_id="test-2", context="unit"
            )


class TestAudioNeedsMp3UploadForStt:
    def test_m4a_by_suffix(self) -> None:
        assert audio_needs_mp3_upload_for_stt(file_name="v.m4a", content_type="audio/mp4") is True

    def test_mp4_content_type(self) -> None:
        assert audio_needs_mp3_upload_for_stt(file_name="x.bin", content_type="video/mp4") is True

    def test_wav_false(self) -> None:
        assert audio_needs_mp3_upload_for_stt(file_name="v.wav", content_type="audio/wav") is False


class TestNormalizeAudioToMp3ForStt:
    def test_wav_to_mp3(self) -> None:
        wav = minimal_wav_silence(duration_sec=0.5)
        mp3_bytes, name = normalize_audio_to_mp3_for_stt(
            audio_bytes=wav,
            file_name="a.wav",
            content_type="audio/wav",
            chunk_bitrate_kbps=32,
            chunk_sample_rate_hz=16000,
            chunk_channels=1,
        )
        assert name == "a.mp3"
        assert len(mp3_bytes) > 100
        assert mp3_bytes[:3] == b"ID3" or mp3_bytes[:2] == b"\xff\xfb" or mp3_bytes[:2] == b"\xff\xf3"


class TestIsSttFormatNotRecognizedError:
    def test_true_for_format_error(self) -> None:
        err = ValueError("Error: format not recognised")
        assert is_stt_format_not_recognized_error(err) is True

    def test_false_for_other_error(self) -> None:
        err = ValueError("Connection timeout")
        assert is_stt_format_not_recognized_error(err) is False


class TestIsYouTubeUrl:
    def test_standard_watch(self) -> None:
        assert is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is True

    def test_short(self) -> None:
        assert is_youtube_url("https://youtu.be/dQw4w9WgXcQ") is True

    def test_not_youtube(self) -> None:
        assert is_youtube_url("https://example.com/video.mp4") is False

    def test_music_youtube(self) -> None:
        assert is_youtube_url("https://music.youtube.com/watch?v=abc123") is True


@pytest.mark.asyncio
class TestMediaTranscriberAudio:
    async def test_transcribe_wav_with_mock_stt(self, unique_id: str) -> None:
        wav = minimal_wav_silence(duration_sec=1.0)
        transcriber = MediaTranscriber(company_id=_mock_stt_tier_company_id(unique_id))
        result = await transcriber.transcribe_audio(
            audio_bytes=wav,
            file_name="voice.wav",
            content_type="audio/wav",
        )
        assert isinstance(result, TranscriptionResult)
        assert len(result.text) > 0

    async def test_raises_on_empty_audio(self, unique_id: str) -> None:
        transcriber = MediaTranscriber(company_id=_mock_stt_tier_company_id(unique_id))
        with pytest.raises(ValueError, match="audio_bytes"):
            await transcriber.transcribe_audio(
                audio_bytes=b"",
                file_name="voice.wav",
                content_type="audio/wav",
            )

    async def test_raises_on_empty_filename(self, unique_id: str) -> None:
        transcriber = MediaTranscriber(company_id=_mock_stt_tier_company_id(unique_id))
        with pytest.raises(ValueError, match="file_name"):
            await transcriber.transcribe_audio(
                audio_bytes=b"\x00\x01",
                file_name="",
                content_type="audio/wav",
            )


@pytest.mark.asyncio
class TestMediaTranscriberVideo:
    async def test_transcribe_mp4_with_mock_stt(self, unique_id: str) -> None:
        video_bytes = _generate_test_mp4(duration_sec=1.0)
        transcriber = MediaTranscriber(company_id=_mock_stt_tier_company_id(unique_id))
        result = await transcriber.transcribe_video(
            video_bytes=video_bytes,
            file_name="call.mp4",
        )
        assert isinstance(result, TranscriptionResult)
        assert len(result.text) > 0

    async def test_raises_on_empty_video(self, unique_id: str) -> None:
        transcriber = MediaTranscriber(company_id=_mock_stt_tier_company_id(unique_id))
        with pytest.raises(ValueError, match="video_bytes"):
            await transcriber.transcribe_video(
                video_bytes=b"",
                file_name="call.mp4",
            )


@pytest.mark.asyncio
class TestFileReaderAudioVideo:
    async def test_recognize_audio_by_extension(self) -> None:
        reader = FileReader()
        info = reader.recognize_file_type(file_name="recording.mp3")
        assert info.detected_kind == FileReadKind.AUDIO

    async def test_recognize_video_by_extension(self) -> None:
        reader = FileReader()
        info = reader.recognize_file_type(file_name="meeting.mp4")
        assert info.detected_kind == FileReadKind.VIDEO

    async def test_recognize_audio_by_mime(self) -> None:
        reader = FileReader()
        info = reader.recognize_file_type(file_name="file.xyz")
        assert info.detected_kind == FileReadKind.UNKNOWN
        info2 = reader.recognize_file_type(file_name="file.ogg")
        assert info2.detected_kind == FileReadKind.AUDIO

    async def test_recognize_video_extensions(self) -> None:
        reader = FileReader()
        for ext in (".mp4", ".mkv", ".avi", ".mov", ".webm"):
            info = reader.recognize_file_type(file_name=f"file{ext}")
            assert info.detected_kind == FileReadKind.VIDEO, f"Failed for {ext}"

    async def test_recognize_audio_extensions(self) -> None:
        reader = FileReader()
        for ext in (".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac", ".wma", ".opus", ".amr"):
            info = reader.recognize_file_type(file_name=f"file{ext}")
            assert info.detected_kind == FileReadKind.AUDIO, f"Failed for {ext}"

    async def test_read_wav_returns_transcription(self, unique_id: str) -> None:
        wav = minimal_wav_silence(duration_sec=1.0)
        reader = FileReader()
        result = await reader.read(
            wav,
            file_name="voice.wav",
            transcription_company_id=_mock_stt_tier_company_id(unique_id),
        )
        assert result.detected_kind == FileReadKind.AUDIO
        assert result.page_count == 1
        assert len(result.pages) == 1
        assert len(result.pages[0].text) > 0

    async def test_read_mp4_returns_transcription(self, unique_id: str) -> None:
        video_bytes = _generate_test_mp4(duration_sec=1.0)
        reader = FileReader()
        result = await reader.read(
            video_bytes,
            file_name="meeting.mp4",
            transcription_company_id=_mock_stt_tier_company_id(unique_id),
        )
        assert result.detected_kind == FileReadKind.VIDEO
        assert result.page_count == 1
        assert len(result.pages) == 1
        assert len(result.pages[0].text) > 0
