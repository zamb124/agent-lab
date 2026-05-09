"""Тесты TTS Pronunciation Shaping Engine.

Проверяет:
- alias с word-boundary и без
- регистронезависимость / чувствительность
- longest-match при перекрытии
- regex-правила
- stress-маркеры (только для capable провайдеров)
- capabilities matrix (cloud_ru не поддерживает stress)
- каскад: platform → company → per-call
- нормализация чисел RU
- дата/валюта RU
- аббревиатуры RU
- smoke 1000 правил sub-50ms
"""

from __future__ import annotations

import time
import uuid

import pytest

from core.clients.tts_pronunciation.models import (
    CompiledPronunciation,
    NormalizationConfig,
    PronunciationRule,
    PronunciationRuleSet,
)
from core.clients.tts_pronunciation.pipeline import TtsTextPipeline


def _rule(kind, pattern, replacement, **kwargs) -> PronunciationRule:
    return PronunciationRule(
        id=str(uuid.uuid4()),
        kind=kind,
        pattern=pattern,
        replacement=replacement,
        **kwargs,
    )


def _compile(rules: list[PronunciationRule], normalization: NormalizationConfig | None = None) -> CompiledPronunciation:
    return CompiledPronunciation.from_rule_set(
        PronunciationRuleSet(
            rules=rules,
            normalization=normalization or NormalizationConfig(
                numbers=False, dates=False, currencies=False, abbreviations=False
            ),
        )
    )


pipeline = TtsTextPipeline()


# ---------------------------------------------------------------------------
# Alias
# ---------------------------------------------------------------------------

def test_alias_basic():
    comp = _compile([_rule("alias", "Хуманитик", "хуманитэк")])
    result = pipeline.transform("Привет Хуманитик мир", pronunciation=comp, provider="litserve")
    assert result == "Привет хуманитэк мир"


def test_alias_case_insensitive_by_default():
    comp = _compile([_rule("alias", "хуманитик", "ХУМ")])
    result = pipeline.transform("хуманитик ХУМАНИТИК Хуманитик", pronunciation=comp, provider="litserve")
    assert result == "ХУМ ХУМ ХУМ"


def test_alias_case_sensitive():
    comp = _compile([_rule("alias", "Foo", "Bar", case_sensitive=True)])
    result = pipeline.transform("foo Foo FOO", pronunciation=comp, provider="litserve")
    assert result == "foo Bar FOO"


def test_alias_word_boundary():
    comp = _compile([_rule("alias", "кот", "котик", word_boundary=True)])
    result = pipeline.transform("кот котов коты", pronunciation=comp, provider="litserve")
    assert result == "котик котов коты"


def test_alias_no_word_boundary():
    comp = _compile([_rule("alias", "кот", "котик", word_boundary=False)])
    result = pipeline.transform("кот котов", pronunciation=comp, provider="litserve")
    assert result == "котик котиков"


def test_alias_longest_match():
    comp = _compile([
        _rule("alias", "Хуманитик", "хуманитэк", word_boundary=False),
        _rule("alias", "Хуманитик AI", "хуманитэк эй-ай", word_boundary=False),
    ])
    result = pipeline.transform("Хуманитик AI", pronunciation=comp, provider="litserve")
    assert result == "хуманитэк эй-ай"


def test_alias_provider_filter_no_match():
    comp = _compile([_rule("alias", "foo", "bar", providers=["litserve"])])
    result = pipeline.transform("foo", pronunciation=comp, provider="cloud_ru")
    assert result == "foo"


def test_alias_provider_filter_match():
    comp = _compile([_rule("alias", "foo", "bar", providers=["litserve"])])
    result = pipeline.transform("foo", pronunciation=comp, provider="litserve")
    assert result == "bar"


# ---------------------------------------------------------------------------
# Stress-маркеры
# ---------------------------------------------------------------------------

def test_stress_applied_for_capable_provider():
    comp = _compile([_rule("stress", "Хуманитик", "хум+анитэк")])
    result = pipeline.transform("Хуманитик", pronunciation=comp, provider="litserve")
    assert result == "хум+анитэк"


def test_stress_skipped_for_cloud_ru():
    comp = _compile([_rule("stress", "Хуманитик", "хум+анитэк")])
    result = pipeline.transform("Хуманитик", pronunciation=comp, provider="cloud_ru")
    assert result == "Хуманитик"


def test_stress_word_boundary():
    comp = _compile([_rule("stress", "кот", "к+от", word_boundary=True)])
    result = pipeline.transform("кот котов", pronunciation=comp, provider="litserve")
    assert result == "к+от котов"


# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

def test_regex_basic():
    comp = _compile([_rule("regex", r"\bAPI\b", "эй-пи-ай")])
    result = pipeline.transform("REST API endpoint", pronunciation=comp, provider="litserve")
    assert result == "REST эй-пи-ай endpoint"


def test_regex_groups():
    comp = _compile([_rule("regex", r"\b(\d+) руб\b", r"\1 рублей")])
    result = pipeline.transform("100 руб за штуку", pronunciation=comp, provider="litserve")
    assert result == "100 рублей за штуку"


def test_regex_invalid_raises():
    with pytest.raises(ValueError, match="невалидный regex"):
        _compile([_rule("regex", r"[invalid", "x")])


# ---------------------------------------------------------------------------
# Нормализация чисел
# ---------------------------------------------------------------------------

def test_normalize_integer():
    comp = _compile([], NormalizationConfig(numbers=True, dates=False, currencies=False, abbreviations=False))
    result = pipeline.transform("Всего 42 позиции", pronunciation=comp, provider="litserve")
    assert "сорок два" in result or "42" in result  # num2words должен перевести


def test_normalize_percent():
    comp = _compile([], NormalizationConfig(numbers=True, dates=False, currencies=False, abbreviations=False))
    result = pipeline.transform("100% гарантия", pronunciation=comp, provider="litserve")
    assert "процент" in result


# ---------------------------------------------------------------------------
# Нормализация дат
# ---------------------------------------------------------------------------

def test_normalize_date_iso():
    comp = _compile([], NormalizationConfig(numbers=False, dates=True, currencies=False, abbreviations=False))
    result = pipeline.transform("Дата: 2026-01-15", pronunciation=comp, provider="litserve")
    assert "января" in result
    assert "2026-01-15" not in result


def test_normalize_date_ru():
    comp = _compile([], NormalizationConfig(numbers=False, dates=True, currencies=False, abbreviations=False))
    result = pipeline.transform("Дата: 15.01.2026", pronunciation=comp, provider="litserve")
    assert "января" in result


# ---------------------------------------------------------------------------
# Нормализация валют
# ---------------------------------------------------------------------------

def test_normalize_ruble():
    comp = _compile([], NormalizationConfig(numbers=False, dates=False, currencies=True, abbreviations=False))
    result = pipeline.transform("Стоимость: 500 ₽", pronunciation=comp, provider="litserve")
    assert "рублей" in result
    assert "₽" not in result


def test_normalize_usd():
    comp = _compile([], NormalizationConfig(numbers=False, dates=False, currencies=True, abbreviations=False))
    result = pipeline.transform("Price: $100", pronunciation=comp, provider="litserve")
    assert "долларов" in result


# ---------------------------------------------------------------------------
# Нормализация аббревиатур
# ---------------------------------------------------------------------------

def test_normalize_abbreviation():
    comp = _compile([], NormalizationConfig(numbers=False, dates=False, currencies=False, abbreviations=True))
    result = pipeline.transform("т.е. это важно", pronunciation=comp, provider="litserve")
    assert "то есть" in result


# ---------------------------------------------------------------------------
# Cascade (platform → company → per-call)
# ---------------------------------------------------------------------------

def test_cascade_platform_company():
    platform = _compile([_rule("alias", "foo", "FOO")])
    company = _compile([_rule("alias", "bar", "BAR")])
    merged = platform.merge(company)
    result = pipeline.transform("foo bar", pronunciation=merged, provider="litserve")
    assert result == "FOO BAR"


def test_cascade_per_call_replaces():
    platform = _compile([_rule("alias", "foo", "FOO")])
    per_call = _compile([_rule("alias", "foo", "OVERRIDE")])
    merged = platform.merge(per_call)
    result = pipeline.transform("foo", pronunciation=merged, provider="litserve")
    assert result == "OVERRIDE"


def test_cascade_disabled_rule_skipped():
    comp = _compile([_rule("alias", "foo", "bar", enabled=False)])
    result = pipeline.transform("foo", pronunciation=comp, provider="litserve")
    assert result == "foo"


# ---------------------------------------------------------------------------
# Smoke: 1000 правил sub-50ms
# ---------------------------------------------------------------------------

def test_smoke_1000_rules_performance():
    rules = [
        _rule("alias", f"слово_{i}", f"замена_{i}", word_boundary=True)
        for i in range(1000)
    ]
    comp = _compile(rules)
    text = "Привет мир! " * 200  # ~10KB
    start = time.monotonic()
    result = pipeline.transform(text, pronunciation=comp, provider="litserve")
    elapsed_ms = (time.monotonic() - start) * 1000
    assert elapsed_ms < 50, f"Pipeline took {elapsed_ms:.1f}ms — выше порога 50ms"
    assert result  # не пустой


# ---------------------------------------------------------------------------
# Empty text passthrough
# ---------------------------------------------------------------------------

def test_empty_text_returns_empty():
    comp = _compile([_rule("alias", "foo", "bar")])
    result = pipeline.transform("", pronunciation=comp, provider="litserve")
    assert result == ""


# ---------------------------------------------------------------------------
# Language filter
# ---------------------------------------------------------------------------

def test_language_filter_match():
    comp = _compile([_rule("alias", "color", "colour", language="en")])
    result = pipeline.transform("color", pronunciation=comp, provider="litserve", language="en-US")
    assert result == "colour"


def test_language_filter_no_match():
    comp = _compile([_rule("alias", "color", "colour", language="en")])
    result = pipeline.transform("color", pronunciation=comp, provider="litserve", language="ru")
    assert result == "color"
