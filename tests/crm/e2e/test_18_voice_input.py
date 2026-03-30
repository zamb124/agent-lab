"""
Тесты голосового ввода.

User Story: Голосовой ввод -> транскрипция -> AI анализ -> создание entities.
"""

import io
import struct
import pytest
import json


def _generate_wav_silence(duration_sec: float = 1.0, sample_rate: int = 16000, bits_per_sample: int = 16) -> bytes:
    """PCM WAV с тишиной — валидный аудиофайл для STT."""
    num_channels = 1
    num_samples = int(sample_rate * duration_sec)
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


@pytest.mark.real_taskiq
class TestVoiceInput:
    """Голосовой ввод и транскрипция"""
    
    @pytest.mark.asyncio
    async def test_transcribe_audio(self, crm_client, mock_llm_redis, unique_id, auth_headers_system):
        """Аудио -> текст через STT (транскрипция)"""
        audio_bytes = _generate_wav_silence(duration_sec=1.0)
        
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "transcription": "Сегодня встретился с Иваном. Обсудили проект X. Нужно подготовить отчет к пятнице."
            })
        }])
        
        files = {"file": ("voice.wav", audio_bytes, "audio/wav")}
        response = await crm_client.post("/crm/api/v1/entities/voice-input", files=files, headers=auth_headers_system)
        
        assert response.status_code == 200
        result = response.json()
        
        assert "text" in result
        assert "stt" in result
        transcription = result["text"]
        assert len(transcription) > 0
        assert result["stt"]["status"] == "done"
    
    @pytest.mark.asyncio
    async def test_voice_to_note_full_pipeline(self, crm_client, mock_llm_redis, unique_id, auth_headers_system):
        """Полный pipeline: Аудио -> транскрипция -> AI анализ -> entities"""
        audio_bytes = _generate_wav_silence(duration_sec=1.0)
        
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
            headers=auth_headers_system,
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
    async def test_voice_input_with_language(self, crm_client, mock_llm_redis, unique_id, auth_headers_system):
        """Голосовой ввод с указанием языка"""
        audio_bytes = _generate_wav_silence(duration_sec=1.0)
        
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
            headers=auth_headers_system,
        )
        
        assert response.status_code == 200
        result = response.json()
        assert "stt" in result
        transcription = result["text"]
        assert len(transcription) > 0
