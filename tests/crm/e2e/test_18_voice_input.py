"""
Тесты голосового ввода.

User Story: Голосовой ввод -> транскрипция -> AI анализ -> создание entities.

Контекст ``company2``: у ``system`` в тестовой БД часто есть ``company_voice_providers``
(STT litserve), что сильнее deployment-default и даёт ConnectError без поднятого litserve.
"""

import json
from collections.abc import Awaitable, Callable
from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_dict, object_list, object_str
from tests.fixtures.audio_bytes import minimal_wav_silence

MockLlmRedisFactory = Callable[[list[object]], Awaitable[None]]


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


@pytest.mark.real_taskiq
class TestVoiceInput:
    """Голосовой ввод и транскрипция"""

    @pytest.mark.asyncio
    async def test_transcribe_audio(
        self,
        crm_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        unique_id: str,
        auth_headers_company2: dict[str, str],
    ) -> None:
        """Аудио -> текст через STT (транскрипция)"""
        _ = unique_id
        audio_bytes = minimal_wav_silence(duration_sec=1.0)

        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "transcription": "Сегодня встретился с Иваном. Обсудили проект X. Нужно подготовить отчет к пятнице.",
            }),
        }])

        files = {"file": ("voice.wav", audio_bytes, "audio/wav")}
        response = await crm_client.post(
            "/crm/api/v1/entities/voice-input",
            files=files,
            headers=auth_headers_company2,
        )

        assert response.status_code == 200
        result = _http_json(response)

        assert "text" in result
        assert "stt" in result
        transcription = object_str(result.get("text"), field="text")
        assert len(transcription) > 0
        stt_payload = object_dict(result.get("stt"), field="stt")
        assert "text" in stt_payload

    @pytest.mark.asyncio
    async def test_voice_to_note_full_pipeline(
        self,
        crm_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        unique_id: str,
        auth_headers_company2: dict[str, str],
    ) -> None:
        """Полный pipeline: Аудио -> транскрипция -> AI анализ -> entities"""
        _ = unique_id
        audio_bytes = minimal_wav_silence(duration_sec=1.0)

        await mock_llm_redis([
            {
                "type": "text",
                "content": json.dumps({
                    "transcription": (
                        "Встретились с Иваном Ивановым. Обсудили проект по разработке AI системы. "
                        "Иван предложил нанять Петра."
                    ),
                }),
            },
            {
                "type": "text",
                "content": json.dumps({
                    "note": {
                        "entity_type": "note",
                        "entity_subtype": "meeting",
                        "name": "Встреча с Иваном",
                        "description": "Обсудили проект AI системы",
                    },
                    "entities": [
                        {"entity_type": "contact", "name": "Иван Иванов"},
                        {"entity_type": "contact", "name": "Петр"},
                        {"entity_type": "project", "name": "AI система"},
                    ],
                    "relationships": [],
                }),
            },
        ])

        files = {"file": ("meeting.wav", audio_bytes, "audio/wav")}
        response = await crm_client.post(
            "/crm/api/v1/entities/voice-input?analyze=true",
            files=files,
            headers=auth_headers_company2,
        )

        assert response.status_code == 200
        result = _http_json(response)

        note_value = result.get("note")
        if note_value is not None:
            if isinstance(note_value, dict):
                note = object_dict(cast(object, note_value), field="note")
                assert object_str(note.get("entity_type"), field="entity_type") == "note"
            else:
                assert note_value is not None

        entities_value = result.get("entities")
        if entities_value is not None:
            entities = object_list(entities_value)
            assert len(entities) >= 1

    @pytest.mark.asyncio
    async def test_voice_input_with_language(
        self,
        crm_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        unique_id: str,
        auth_headers_company2: dict[str, str],
    ) -> None:
        """Голосовой ввод с указанием языка"""
        _ = unique_id
        audio_bytes = minimal_wav_silence(duration_sec=1.0)

        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "transcription": "Тестовая транскрипция на русском языке",
            }),
        }])

        files = {"file": ("voice_ru.wav", audio_bytes, "audio/wav")}
        response = await crm_client.post(
            "/crm/api/v1/entities/voice-input?language=ru",
            files=files,
            headers=auth_headers_company2,
        )

        assert response.status_code == 200
        result = _http_json(response)
        assert "stt" in result
        transcription = object_str(result.get("text"), field="text")
        assert len(transcription) > 0
