"""Совместимый реэкспорт ``VoiceChunker`` из core.

Канон: ``core.clients.voice_chunker.VoiceChunker`` — один класс чанкинга для
всей платформы (voice real-time сессия и streaming TTS в ``core/clients``).
Импорт из ``apps.voice.services.voice_chunker`` остаётся валидным для
совместимости с текущим кодом сервиса voice.
"""

from __future__ import annotations

from core.clients.voice_chunker import VoiceChunker

__all__ = ["VoiceChunker"]
