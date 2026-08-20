"""_replace_audio_transcription: DONE → text/plain origin=speech + audio; пустой STT — без text."""

from __future__ import annotations

from apps.sync.models.messages import (
    MessageContentModel,
    MessageContentType,
    TextPlainContent,
)
from apps.sync.realtime.tasks import _replace_audio_transcription
from core.files.models import (
    STT_FAILED_ERROR_CODE,
    AudioAttachmentContent,
    AudioTranscriptionStatus,
)


def _audio_block(*, transcript: str | None = None) -> MessageContentModel:
    return MessageContentModel(
        type=MessageContentType.FILE_AUDIO,
        data=AudioAttachmentContent(
            file_id="file_audio_1",
            original_name="note.wav",
            content_type="audio/wav",
            file_size=128,
            duration_ms=800,
            waveform=None,
            transcription_status=AudioTranscriptionStatus.PROCESSING,
            transcription_text=transcript,
            transcription_error=None,
            source_speech_to_chat=True,
        ),
        order=0,
    )


def test_replace_audio_transcription_done_adds_speech_text() -> None:
    contents = _replace_audio_transcription(
        contents=[_audio_block()],
        status=AudioTranscriptionStatus.DONE,
        transcription_text="  привет  ",
        transcription_error=None,
    )
    assert len(contents) == 2
    text_block = contents[0]
    audio_block = contents[1]
    assert text_block.type == MessageContentType.TEXT_PLAIN
    assert isinstance(text_block.data, TextPlainContent)
    assert text_block.data.origin == "speech"
    assert text_block.data.body == "привет"
    assert text_block.order == 0
    assert audio_block.type == MessageContentType.FILE_AUDIO
    assert isinstance(audio_block.data, AudioAttachmentContent)
    assert audio_block.data.transcription_status == AudioTranscriptionStatus.DONE
    assert audio_block.data.transcription_text == "  привет  "
    assert audio_block.order == 1


def test_replace_audio_transcription_empty_stt_skips_text_block() -> None:
    contents = _replace_audio_transcription(
        contents=[_audio_block()],
        status=AudioTranscriptionStatus.DONE,
        transcription_text="   ",
        transcription_error=None,
    )
    assert len(contents) == 1
    assert contents[0].type == MessageContentType.FILE_AUDIO
    assert isinstance(contents[0].data, AudioAttachmentContent)
    assert contents[0].data.transcription_status == AudioTranscriptionStatus.DONE


def test_replace_audio_transcription_failed_uses_stt_code_and_drops_speech_text() -> None:
    previous = [
        MessageContentModel(
            type=MessageContentType.TEXT_PLAIN,
            data=TextPlainContent(body="старый", mentions=None, origin="speech"),
            order=0,
        ),
        _audio_block(transcript="старый"),
    ]
    contents = _replace_audio_transcription(
        contents=previous,
        status=AudioTranscriptionStatus.FAILED,
        transcription_text=None,
        transcription_error=STT_FAILED_ERROR_CODE,
    )
    assert len(contents) == 1
    assert contents[0].type == MessageContentType.FILE_AUDIO
    assert isinstance(contents[0].data, AudioAttachmentContent)
    assert contents[0].data.transcription_status == AudioTranscriptionStatus.FAILED
    assert contents[0].data.transcription_error == STT_FAILED_ERROR_CODE
    assert "500" not in (contents[0].data.transcription_error or "")
