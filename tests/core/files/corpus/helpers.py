"""Вспомогательные функции для тестов корпуса."""

from __future__ import annotations

import pytest

from tests.core.files.corpus.models import CORPUS_DIR


def corpus_stt_company_id(unique_id: str) -> str:
    """company_id без строки в company_voice_providers → STT резолвится в mock-провайдер.

    Тот же паттерн, что в test_media_transcriber.py.
    """
    return f"corpus_stt_tier_{unique_id}"


def require_heic_decode_support() -> None:
    """Runtime skip для HEIC, если pillow_heif/libheif недоступны на платформе."""
    heic_path = CORPUS_DIR / "img" / "DA-1p.heic"
    if not heic_path.is_file():
        pytest.skip("HEIC corpus file missing")
    try:
        import pillow_heif
        from PIL import Image

        pillow_heif.register_heif_opener()
        with Image.open(heic_path) as image:
            image.load()
    except Exception as exc:
        pytest.skip(f"HEIC decode unavailable: {exc}")


def require_heic_entry_supported(relative_path: str) -> None:
    if relative_path == "img/DA-1p.heic":
        require_heic_decode_support()
