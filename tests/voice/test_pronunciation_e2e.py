"""E2E тесты pronunciation pipeline через mock TTS провайдер.

Проверяет, что PronunciationAwareTTSClient корректно трансформирует текст
перед вызовом базового клиента.
"""

from __future__ import annotations

import uuid

import pytest

from core.clients.tts_client import MockTTSClient, PronunciationAwareTTSClient
from core.clients.tts_pronunciation.models import (
    CompiledPronunciation,
    NormalizationConfig,
    PronunciationRule,
    PronunciationRuleSet,
)


def _compile_rules(rules: list[PronunciationRule]) -> CompiledPronunciation:
    return CompiledPronunciation.from_rule_set(
        PronunciationRuleSet(
            rules=rules,
            normalization=NormalizationConfig(
                numbers=False, dates=False, currencies=False, abbreviations=False
            ),
        )
    )


def _rule(kind, pattern, replacement, **kwargs) -> PronunciationRule:
    return PronunciationRule(
        id=str(uuid.uuid4()),
        kind=kind,
        pattern=pattern,
        replacement=replacement,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_pronunciation_aware_client_transforms_text():
    """PronunciationAwareTTSClient применяет alias-правило перед синтезом."""
    compiled = _compile_rules([_rule("alias", "Хуманитик", "хуманитэк")])
    received_texts: list[str] = []

    class _CapturingMock(MockTTSClient):
        async def synthesize(self, *, text, **kwargs):
            received_texts.append(text)
            return await super().synthesize(text=text, **kwargs)

    client = PronunciationAwareTTSClient(
        _CapturingMock(),
        compiled,
        provider_name="mock",
    )
    await client.synthesize(text="Привет Хуманитик мир")
    assert len(received_texts) == 1
    assert "хуманитэк" in received_texts[0]
    assert "Хуманитик" not in received_texts[0]


@pytest.mark.asyncio
async def test_pronunciation_aware_client_empty_rules_passthrough():
    """Без правил текст проходит без изменений."""
    compiled = CompiledPronunciation.empty()
    received_texts: list[str] = []

    class _CapturingMock(MockTTSClient):
        async def synthesize(self, *, text, **kwargs):
            received_texts.append(text)
            return await super().synthesize(text=text, **kwargs)

    client = PronunciationAwareTTSClient(
        _CapturingMock(),
        compiled,
        provider_name="mock",
    )
    original = "Hello World"
    await client.synthesize(text=original)
    assert received_texts[0] == original


@pytest.mark.asyncio
async def test_pronunciation_aware_stress_skipped_for_cloud_ru():
    """Stress-правило не применяется для cloud_ru."""
    compiled = _compile_rules([_rule("stress", "Хуманитик", "хум+анитэк")])
    received_texts: list[str] = []

    class _CapturingMock(MockTTSClient):
        async def synthesize(self, *, text, **kwargs):
            received_texts.append(text)
            return await super().synthesize(text=text, **kwargs)

    client = PronunciationAwareTTSClient(
        _CapturingMock(),
        compiled,
        provider_name="cloud_ru",
    )
    await client.synthesize(text="Хуманитик платформа")
    assert "+" not in received_texts[0]
    assert "Хуманитик" in received_texts[0]


@pytest.mark.asyncio
async def test_pronunciation_aware_multiple_rules():
    """Несколько правил применяются по порядку."""
    compiled = _compile_rules([
        _rule("alias", "foo", "бар"),
        _rule("alias", "baz", "кей"),
    ])
    received_texts: list[str] = []

    class _CapturingMock(MockTTSClient):
        async def synthesize(self, *, text, **kwargs):
            received_texts.append(text)
            return await super().synthesize(text=text, **kwargs)

    client = PronunciationAwareTTSClient(
        _CapturingMock(),
        compiled,
        provider_name="mock",
    )
    await client.synthesize(text="foo and baz")
    assert "бар" in received_texts[0]
    assert "кей" in received_texts[0]


@pytest.mark.asyncio
async def test_pronunciation_aware_provider_filter():
    """Правило с providers=[litserve] не применяется для mock."""
    compiled = _compile_rules([_rule("alias", "hello", "привет", providers=["litserve"])])
    received_texts: list[str] = []

    class _CapturingMock(MockTTSClient):
        async def synthesize(self, *, text, **kwargs):
            received_texts.append(text)
            return await super().synthesize(text=text, **kwargs)

    client = PronunciationAwareTTSClient(
        _CapturingMock(),
        compiled,
        provider_name="mock",
    )
    await client.synthesize(text="hello world")
    assert "hello" in received_texts[0]
    assert "привет" not in received_texts[0]
