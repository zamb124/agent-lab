"""Вспомогательные функции для тестов корпуса."""

from __future__ import annotations


def corpus_stt_company_id(unique_id: str) -> str:
    """company_id без строки в company_voice_providers → STT резолвится в mock-провайдер.

    Тот же паттерн, что в test_media_transcriber.py.
    """
    return f"corpus_stt_tier_{unique_id}"
