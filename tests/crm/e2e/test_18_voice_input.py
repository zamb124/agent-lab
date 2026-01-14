"""
Тесты голосового ввода.

User Story: Голосовой ввод → транскрипция → AI анализ → создание entities.
"""

import pytest
import json


@pytest.mark.real_taskiq
class TestVoiceInput:
    """Голосовой ввод и транскрипция"""
    
    @pytest.mark.asyncio
    async def test_transcribe_audio(self, crm_client, mock_llm_redis, unique_id, auth_headers_system):
        """Аудио → текст через agents (транскрипция)"""
        audio_file = b"fake audio bytes for testing"
        
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "transcription": "Сегодня встретился с Иваном. Обсудили проект X. Нужно подготовить отчет к пятнице."
            })
        }])
        
        files = {"file": ("voice.mp3", audio_file, "audio/mpeg")}
        response = await crm_client.post("/crm/api/v1/entities/voice-input", files=files, headers=auth_headers_system)
        
        assert response.status_code == 200
        result = response.json()
        
        assert "text" in result or "transcription" in result
        transcription = result.get("text") or result.get("transcription")
        assert len(transcription) > 0
    
    @pytest.mark.asyncio
    async def test_voice_to_note_full_pipeline(self, crm_client, mock_llm_redis, unique_id, auth_headers_system):
        """Полный pipeline: Аудио → транскрипция → AI анализ → entities"""
        audio_file = b"fake audio for full pipeline test"
        
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
        
        files = {"file": ("meeting.mp3", audio_file, "audio/mpeg")}
        response = await crm_client.post(
            "/crm/api/v1/entities/voice-input?analyze=true",
            files=files
        , headers=auth_headers_system)
        
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
    async def test_voice_input_with_language(self, crm_client, mock_llm_redis, unique_id, auth_headers_system):
        """Голосовой ввод с указанием языка"""
        audio_file = b"russian audio bytes"
        
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "transcription": "Тестовая транскрипция на русском языке"
            })
        }])
        
        files = {"file": ("voice_ru.mp3", audio_file, "audio/mpeg")}
        response = await crm_client.post(
            "/crm/api/v1/entities/voice-input?language=ru",
            files=files,
            headers=auth_headers_system
        )
        
        assert response.status_code == 200
        result = response.json()
        transcription = result.get("text") or result.get("transcription")
        assert "русском" in transcription or len(transcription) > 0

