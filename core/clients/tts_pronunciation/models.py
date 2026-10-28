"""Модели данных TTS Pronunciation Shaping Engine."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar, Literal, Self, override

from oxyde import Field as DbField
from oxyde import Index
from pydantic import BaseModel, ConfigDict, Field

from core.models.platform_model import PlatformModel

PronunciationRuleKind = Literal["alias", "regex", "stress"]


def _company_scope(company_id: str | None) -> str | None:
    if company_id is None:
        return None
    if company_id == "":
        raise ValueError("company_id cannot be empty.")
    return company_id


def _rule_id(rule_id: str) -> str:
    if rule_id == "":
        raise ValueError("rule_id cannot be empty.")
    return rule_id


class PronunciationRule(PlatformModel):
    """Одно правило подмены текста перед TTS. Таблица ``pronunciation_rules`` в ``platform_shared``.

    ``company_id is None`` — правило платформы. Иначе правило компании.
    Per-call правила в ``SpeechOverride`` — тот же класс и не сохраняются.

    * ``alias`` — точная подстрока (word-boundary опционален), longest-match.
    * ``regex`` — ``re.Pattern``; replacement может содержать группы ``\\1``, ``\\2``.
    * ``stress`` — alias с ``+`` перед ударной гласной в ``replacement``.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    pronunciation_rule_id: str = DbField(default="", db_pk=True, max_length=36)

    class Meta:
        is_table: bool = True
        table_name: str = "pronunciation_rules"
        indexes: list[Index] = [
            Index(("company_id", "enabled")),
            Index(("enabled",)),
            Index(("language",)),
            Index(("created_at",)),
        ]

    company_id: str | None = DbField(default=None, db_index=True, max_length=255)
    kind: PronunciationRuleKind = DbField(max_length=16)
    pattern: str = DbField(min_length=1, db_type="TEXT")
    replacement: str = DbField(db_type="TEXT")
    language: str | None = DbField(default=None, max_length=16)
    case_sensitive: bool = DbField(default=False)
    word_boundary: bool = DbField(default=True)
    providers: list[str] | None = DbField(default=None, db_type="JSONB")
    voices: list[str] | None = DbField(default=None, db_type="JSONB")
    enabled: bool = DbField(default=True)
    note: str | None = DbField(default=None, db_type="TEXT")
    created_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = update_fields
        if self.pattern == "":
            raise ValueError("pattern cannot be empty.")
        if self.pronunciation_rule_id == "":
            self.pronunciation_rule_id = str(uuid.uuid4())
        if is_create and "created_at" not in self.model_fields_set:
            self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    @classmethod
    async def list_for_company_scope(cls, *, company_id: str | None) -> list[Self]:
        """Строки одного scope, ORDER BY created_at, без limit. company_id None — платформа (company_id IS NULL). Пустая строка — ValueError."""
        return await cls.objects.filter(
            company_id=_company_scope(company_id),
        ).order_by("created_at").all()

    @classmethod
    async def list_enabled_for_company_scope(cls, *, company_id: str | None) -> list[Self]:
        """Включённые строки одного scope, ORDER BY created_at, без limit. company_id None — платформа. Пустая строка — ValueError."""
        return await cls.objects.filter(
            company_id=_company_scope(company_id),
            enabled=True,
        ).order_by("created_at").all()

    @classmethod
    async def by_company_scope_and_rule_id(
        cls,
        *,
        company_id: str | None,
        rule_id: str,
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=_company_scope(company_id),
            pronunciation_rule_id=_rule_id(rule_id),
        ).get_or_none()

    @classmethod
    async def create_for_company_scope(
        cls,
        *,
        company_id: str | None,
        rule: PronunciationRuleWrite,
        max_rules: int | None = None,
    ) -> Self:
        scoped_company_id = _company_scope(company_id)
        if scoped_company_id is not None:
            if max_rules is None:
                raise ValueError("max_rules is required for a company pronunciation rule.")
            current_count = await cls.objects.filter(company_id=scoped_company_id).count()
            if current_count >= max_rules:
                raise ValueError(
                    f"Pronunciation rule limit reached for company {scoped_company_id!r}: {current_count}/{max_rules}. Remove some rules before adding more."
                )
        now = datetime.now(timezone.utc)
        row = cls(
            company_id=scoped_company_id,
            kind=rule.kind,
            pattern=rule.pattern,
            replacement=rule.replacement,
            language=rule.language,
            case_sensitive=rule.case_sensitive,
            word_boundary=rule.word_boundary,
            providers=rule.providers,
            voices=rule.voices,
            enabled=rule.enabled,
            note=rule.note,
            created_at=now,
            updated_at=now,
        )
        return await cls.objects.create(instance=row)

    @classmethod
    async def update_by_company_scope_and_rule_id(
        cls,
        *,
        company_id: str | None,
        rule_id: str,
        patch: PronunciationRulePatch,
    ) -> Self | None:
        row = await cls.by_company_scope_and_rule_id(company_id=company_id, rule_id=rule_id)
        if row is None:
            return None
        fields = patch.model_fields_set
        if "kind" in fields:
            if patch.kind is None:
                raise ValueError("kind cannot be empty.")
            row.kind = patch.kind
        if "pattern" in fields:
            if patch.pattern is None or patch.pattern == "":
                raise ValueError("pattern cannot be empty.")
            row.pattern = patch.pattern
        if "replacement" in fields:
            if patch.replacement is None:
                raise ValueError("replacement cannot be empty.")
            row.replacement = patch.replacement
        if "language" in fields:
            row.language = patch.language
        if "case_sensitive" in fields:
            if patch.case_sensitive is None:
                raise ValueError("case_sensitive cannot be empty.")
            row.case_sensitive = patch.case_sensitive
        if "word_boundary" in fields:
            if patch.word_boundary is None:
                raise ValueError("word_boundary cannot be empty.")
            row.word_boundary = patch.word_boundary
        if "providers" in fields:
            row.providers = patch.providers
        if "voices" in fields:
            row.voices = patch.voices
        if "enabled" in fields:
            if patch.enabled is None:
                raise ValueError("enabled cannot be empty.")
            row.enabled = patch.enabled
        if "note" in fields:
            row.note = patch.note
        row.updated_at = datetime.now(timezone.utc)
        _ = await row.save()
        return row

    @classmethod
    async def delete_by_company_scope_and_rule_id(
        cls,
        *,
        company_id: str | None,
        rule_id: str,
    ) -> bool:
        deleted = await cls.objects.filter(
            company_id=_company_scope(company_id),
            pronunciation_rule_id=_rule_id(rule_id),
        ).delete()
        return deleted > 0


class PronunciationRuleWrite(BaseModel):
    """Тело создания правила. Компания берётся из пути, не из тела."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    kind: PronunciationRuleKind
    pattern: str = Field(min_length=1)
    replacement: str
    language: str | None = None
    case_sensitive: bool = False
    word_boundary: bool = True
    providers: list[str] | None = None
    voices: list[str] | None = None
    enabled: bool = True
    note: str | None = None


class PronunciationRulePatch(BaseModel):
    """Тело обновления. Поле отсутствует в JSON — колонка не меняется."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    kind: PronunciationRuleKind | None = None
    pattern: str | None = Field(default=None, min_length=1)
    replacement: str | None = None
    language: str | None = None
    case_sensitive: bool | None = None
    word_boundary: bool | None = None
    providers: list[str] | None = None
    voices: list[str] | None = None
    enabled: bool | None = None
    note: str | None = None


class NormalizationConfig(BaseModel):
    """Настройки текстовой нормализации (числа, даты, валюты, аббревиатуры)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    numbers: bool = True
    dates: bool = True
    currencies: bool = True
    abbreviations: bool = True
    locale: str = Field(default="ru", description="ISO 639-1 локаль нормализации.")


class PronunciationRuleSet(BaseModel):
    """Полный набор правил + настройки нормализации для одного контекста."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

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
    providers: frozenset[str] | None
    voices: frozenset[str] | None
    language: str | None


@dataclass
class _CompiledAliasRule:
    pattern: str
    replacement: str
    word_boundary: bool
    case_sensitive: bool
    providers: frozenset[str] | None
    voices: frozenset[str] | None
    language: str | None
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
                        f"PronunciationRule pronunciation_rule_id={rule.pronunciation_rule_id!r}: invalid regex {rule.pattern!r}: {exc}"
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
    "PronunciationRulePatch",
    "PronunciationRuleSet",
    "PronunciationRuleWrite",
    "ProviderCapabilities",
    "_CompiledAliasRule",
    "_CompiledRegexRule",
    "get_provider_capabilities",
]
