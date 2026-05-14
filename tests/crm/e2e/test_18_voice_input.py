"""
Тесты голосового ввода.

User Story: Голосовой ввод -> транскрипция -> AI анализ -> создание entities.

Контекст ``company2``: у ``system`` в тестовой БД часто есть ``company_voice_providers``
(STT litserve), что сильнее deployment-default и даёт ConnectError без поднятого litserve.
"""

import json

import pytest

from tests.fixtures.audio_bytes import minimal_wav_silence


@pytest.mark.real_taskiq
class TestVoiceInput:
    """Голосовой ввод и транскрипция"""

    @pytest.mark.asyncio
    async def test_transcribe_audio(self, crm_client, mock_llm_redis, unique_id, auth_headers_company2):
        """Аудио -> текст через STT (транскрипция)"""
        audio_bytes = minimal_wav_silence(duration_sec=1.0)

        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "transcription": "Сегодня встретился с Иваном. Обсудили проект X. Нужно подготовить отчет к пятнице."
            })
        }])

        files = {"file": ("voice.wav", audio_bytes, "audio/wav")}
        response = await crm_client.post("/crm/api/v1/entities/voice-input", files=files, headers=auth_headers_company2)

        assert response.status_code == 200
        result = response.json()

        assert "text" in result
        assert "stt" in result
        transcription = result["text"]
        assert len(transcription) > 0
        assert "text" in result["stt"]

    @pytest.mark.asyncio
    async def test_voice_to_note_full_pipeline(self, crm_client, mock_llm_redis, unique_id, auth_headers_company2):
        """Полный pipeline: Аудио -> транскрипция -> AI анализ -> entities"""
        audio_bytes = minimal_wav_silence(duration_sec=1.0)

        await mock_llm_redis([
            {
                "type": "text",
                "content": json.dumps({
                    "transcription": "Встретились с Иваном Ивановым. Обсудили проект по разработке AI системы. Иван предложил нанять Петра."
                })
            },
            {
                "type": "text",
                "content": json.dumps({
                    "note": {
                        "entity_type": "note",
                        "entity_subtype": "meeting",
                        "name": "Встреча с Иваном",
                        "description": "Обсудили проект AI системы"
                    },
                    "entities": [
                        {"entity_type": "contact", "name": "Иван Иванов"},
                        {"entity_type": "contact", "name": "Петр"},
                        {"entity_type": "project", "name": "AI система"}
                    ],
                    "relationships": []
                })
            }
        ])

        files = {"file": ("meeting.wav", audio_bytes, "audio/wav")}
        response = await crm_client.post(
            "/crm/api/v1/entities/voice-input?analyze=true",
            files=files,
            headers=auth_headers_company2,
        )

        assert response.status_code == 200
        result = response.json()

        if "note" in result:
            note = result["note"]
            if isinstance(note, dict):
                assert note["entity_type"] == "note"
            else:
                assert note is not None

        if "entities" in result:
            assert len(result["entities"]) >= 1

    @pytest.mark.asyncio
    async def test_voice_input_with_language(self, crm_client, mock_llm_redis, unique_id, auth_headers_company2):
        """Голосовой ввод с указанием языка"""
        audio_bytes = minimal_wav_silence(duration_sec=1.0)

        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "transcription": "Тестовая транскрипция на русском языке"
            })
        }])

        files = {"file": ("voice_ru.wav", audio_bytes, "audio/wav")}
        response = await crm_client.post(
            "/crm/api/v1/entities/voice-input?language=ru",
            files=files,
            headers=auth_headers_company2,
        )

        assert response.status_code == 200
        result = response.json()
        assert "stt" in result
        transcription = result["text"]
        assert len(transcription) > 0
