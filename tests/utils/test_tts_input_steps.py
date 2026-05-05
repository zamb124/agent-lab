"""Шаги подготовки текста для TTS (``tts_input_steps``)."""

from __future__ import annotations

import pytest

from core.utils.tts_input_steps import (
    apply_silero_ru_latin_to_cyrillic,
    apply_tts_input_steps,
)

pytestmark = pytest.mark.timeout(15)


def test_silero_ru_latin_maps_hello_to_cyrillic_letters() -> None:
    out = apply_silero_ru_latin_to_cyrillic("hello")
    assert "а" in out or "о" in out
    assert "h" not in out.lower()


def test_silero_ru_latin_preserves_cyrillic_and_spaces() -> None:
    assert apply_silero_ru_latin_to_cyrillic("Hi мир") == "хи мир"


def test_silero_ru_latin_does_not_use_sch_digraph_for_school() -> None:
    out = apply_silero_ru_latin_to_cyrillic("school")
    assert "щ" not in out


def test_apply_tts_input_steps_unknown_id_raises() -> None:
    with pytest.raises(ValueError, match="Неизвестный"):
        apply_tts_input_steps("x", ("no_such_step",))
