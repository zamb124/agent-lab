"""
Тесты batch-транскрипции voice service (platform voice→text).

UI использует `platform/voice_dictation` → POST /voice/api/v1/transcribe.
Контекст ``company2``: у ``system`` в тестовой БД часто есть ``company_voice_providers``
(STT litserve), что сильнее deployment-default и даёт ConnectError без поднятого litserve.
"""

from collections.abc import Awaitable, Callable
from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_str
from tests.fixtures.audio_bytes import minimal_wav_silence

MockLlmRedisFactory = Callable[[list[object]], Awaitable[None]]


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


@pytest.mark.real_taskiq
class TestVoiceTranscribe:
    """Batch STT через voice gateway."""

    @pytest.mark.asyncio
    async def test_transcribe_audio(
        self,
        voice_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        unique_id: str,
        auth_headers_company2: dict[str, str],
    ) -> None:
        """Аудио -> текст через STT (транскрипция)."""
        _ = unique_id
        audio_bytes = minimal_wav_silence(duration_sec=1.0)

        await mock_llm_redis([{
            "type": "text",
            "content": "Сегодня встретился с Иваном. Обсудили проект X.",
        }])

        files = {"file": ("voice.wav", audio_bytes, "audio/wav")}
        response = await voice_client.post(
            "/voice/api/v1/transcribe",
            files=files,
            headers=auth_headers_company2,
        )

        assert response.status_code == 200
        result = _http_json(response)
        transcription = object_str(result.get("text"), field="text")
        assert len(transcription) > 0
        assert isinstance(result.get("provider"), str)
        assert len(cast(str, result.get("provider"))) > 0

    @pytest.mark.asyncio
    async def test_transcribe_with_language(
        self,
        voice_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        unique_id: str,
        auth_headers_company2: dict[str, str],
    ) -> None:
        """Транскрипция с указанием языка."""
        _ = unique_id
        audio_bytes = minimal_wav_silence(duration_sec=1.0)

        await mock_llm_redis([{
            "type": "text",
            "content": "Тестовая транскрипция на русском языке",
        }])

        files = {"file": ("voice_ru.wav", audio_bytes, "audio/wav")}
        data = {"language": "ru"}
        response = await voice_client.post(
            "/voice/api/v1/transcribe",
            files=files,
            data=data,
            headers=auth_headers_company2,
        )

        assert response.status_code == 200
        result = _http_json(response)
        transcription = object_str(result.get("text"), field="text")
        assert len(transcription) > 0
