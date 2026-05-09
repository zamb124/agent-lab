"""Модели данных TTS Pronunciation Shaping Engine."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


PronunciationRuleKind = Literal["alias", "regex", "stress"]


class PronunciationRule(BaseModel):
    """Одно правило подмены/нормализации текста перед TTS.

    Три вида:
    * ``alias``  — точная подстрока (word-boundary опционален), longest-match.
    * ``regex``  — произвольный ``re.Pattern``; replacement может содержать
      группы ``\\1``, ``\\2``.
    * ``stress`` — alias с символом ``+`` перед ударной гласной в ``replacement``
      (например, ``Хуманитик`` → ``хум+анитэк``); применяется только для
      провайдеров из ``STRESS_CAPABLE_PROVIDERS``.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="UUID правила.")
    kind: PronunciationRuleKind = Field(description="Тип правила.")
    pattern: str = Field(min_length=1, description="Искомое слово / regex-паттерн.")
    replacement: str = Field(description="Замена; для stress — с символом '+' перед ударной гласной.")
    language: Optional[str] = Field(
        default=None,
        description="BCP-47 язык (только ISO 639-1, например 'ru'); None — любой.",
    )
    case_sensitive: bool = Field(default=False)
    word_boundary: bool = Field(
        default=True,
        description="Только для alias/stress: совпадение только на границах слова.",
    )
    providers: Optional[list[str]] = Field(
        default=None,
        description="Whitelist провайдеров; None — все совместимые.",
    )
    voices: Optional[list[str]] = Field(
        default=None,
        description="Whitelist голосов (имён); None — любые.",
    )
    enabled: bool = Field(default=True)
    note: Optional[str] = Field(default=None, description="Комментарий для администратора.")


class NormalizationConfig(BaseModel):
    """Настройки текстовой нормализации (числа, даты, валюты, аббревиатуры)."""

    model_config = ConfigDict(extra="forbid")

    numbers: bool = True
    dates: bool = True
    currencies: bool = True
    abbreviations: bool = True
    locale: str = Field(default="ru", description="ISO 639-1 локаль нормализации.")


class PronunciationRuleSet(BaseModel):
    """Полный набор правил + настройки нормализации для одного контекста."""

    model_config = ConfigDict(extra="forbid")

    rules: list[PronunciationRule] = Field(default_factory=list)
    normalization: NormalizationConfig = Field(default_factory=NormalizationConfig)


# ---------------------------------------------------------------------------
# Возможности провайдеров
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProviderCapabilities:
    """Что поддерживает конкретный TTS-провайдер в части text-shaping."""

    alias: bool = True
    regex: bool = True
    normalization: bool = True
    stress_marker: bool = False
    ssml_phoneme: bool = False


PROVIDER_CAPABILITIES: dict[str, ProviderCapabilities] = {
    "litserve": ProviderCapabilities(
        alias=True, regex=True, normalization=True, stress_marker=True, ssml_phoneme=False
    ),
    "yandex": ProviderCapabilities(
        alias=True, regex=True, normalization=True, stress_marker=True, ssml_phoneme=True
    ),
    "sber": ProviderCapabilities(
        alias=True, regex=True, normalization=True, stress_marker=True, ssml_phoneme=True
    ),
    "cloud_ru": ProviderCapabilities(
        alias=True, regex=True, normalization=True, stress_marker=False, ssml_phoneme=False
    ),
    "mock": ProviderCapabilities(
        alias=True, regex=True, normalization=True, stress_marker=True, ssml_phoneme=True
    ),
}

STRESS_CAPABLE_PROVIDERS: frozenset[str] = frozenset(
    name for name, cap in PROVIDER_CAPABILITIES.items() if cap.stress_marker
)


def get_provider_capabilities(provider: str) -> ProviderCapabilities:
    """Возвращает возможности провайдера; неизвестный провайдер — базовые (alias/regex/norm, без stress)."""
    return PROVIDER_CAPABILITIES.get(
        provider,
        ProviderCapabilities(alias=True, regex=True, normalization=True, stress_marker=False),
    )


# ---------------------------------------------------------------------------
# Скомпилированный набор правил
# ---------------------------------------------------------------------------

@dataclass
class _CompiledRegexRule:
    pattern: re.Pattern[str]
    replacement: str
    providers: Optional[frozenset[str]]
    voices: Optional[frozenset[str]]
    language: Optional[str]


@dataclass
class _CompiledAliasRule:
    pattern: str
    replacement: str
    word_boundary: bool
    case_sensitive: bool
    providers: Optional[frozenset[str]]
    voices: Optional[frozenset[str]]
    language: Optional[str]
    is_stress: bool


@dataclass
class CompiledPronunciation:
    """Предкомпилированный набор правил, готовый к быстрому применению.

    Создаётся однократно при загрузке правил из БД/кэша (в voice_resolver)
    и передаётся в ``TtsTextPipeline.transform`` как аргумент.
    """

    normalization: NormalizationConfig
    regex_rules: list[_CompiledRegexRule] = field(default_factory=list)
    alias_rules: list[_CompiledAliasRule] = field(default_factory=list)
    ssml_subset_enabled: bool = False

    @classmethod
    def empty(cls) -> "CompiledPronunciation":
        return cls(normalization=NormalizationConfig(
            numbers=False, dates=False, currencies=False, abbreviations=False
        ))

    @classmethod
    def from_rule_set(
        cls,
        rule_set: PronunciationRuleSet,
        *,
        ssml_subset_enabled: bool = False,
    ) -> "CompiledPronunciation":
        """Компилирует ``PronunciationRuleSet`` в ``CompiledPronunciation``."""
        regex_rules: list[_CompiledRegexRule] = []
        alias_rules: list[_CompiledAliasRule] = []

        for rule in rule_set.rules:
            if not rule.enabled:
                continue
            providers = frozenset(rule.providers) if rule.providers is not None else None
            voices = frozenset(rule.voices) if rule.voices is not None else None

            if rule.kind == "regex":
                flags = 0 if rule.case_sensitive else re.IGNORECASE
                try:
                    compiled_pat = re.compile(rule.pattern, flags)
                except re.error as exc:
                    raise ValueError(
                        f"PronunciationRule id={rule.id!r}: невалидный regex {rule.pattern!r}: {exc}"
                    ) from exc
                regex_rules.append(_CompiledRegexRule(
                    pattern=compiled_pat,
                    replacement=rule.replacement,
                    providers=providers,
                    voices=voices,
                    language=rule.language,
                ))
            elif rule.kind in ("alias", "stress"):
                alias_rules.append(_CompiledAliasRule(
                    pattern=rule.pattern,
                    replacement=rule.replacement,
                    word_boundary=rule.word_boundary,
                    case_sensitive=rule.case_sensitive,
                    providers=providers,
                    voices=voices,
                    language=rule.language,
                    is_stress=(rule.kind == "stress"),
                ))

        return cls(
            normalization=rule_set.normalization,
            regex_rules=regex_rules,
            alias_rules=alias_rules,
            ssml_subset_enabled=ssml_subset_enabled,
        )

    def merge(self, other: "CompiledPronunciation") -> "CompiledPronunciation":
        """Объединяет два CompiledPronunciation: self — базовый, other — override (append поверх)."""
        return CompiledPronunciation(
            normalization=other.normalization,
            regex_rules=self.regex_rules + other.regex_rules,
            alias_rules=self.alias_rules + other.alias_rules,
            ssml_subset_enabled=other.ssml_subset_enabled or self.ssml_subset_enabled,
        )


__all__ = [
    "CompiledPronunciation",
    "NormalizationConfig",
    "PROVIDER_CAPABILITIES",
    "STRESS_CAPABLE_PROVIDERS",
    "PronunciationRule",
    "PronunciationRuleKind",
    "PronunciationRuleSet",
    "ProviderCapabilities",
    "_CompiledAliasRule",
    "_CompiledRegexRule",
    "get_provider_capabilities",
]
