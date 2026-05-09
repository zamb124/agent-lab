"""TTS Text-Shaping Pipeline.

``TtsTextPipeline.transform`` — единственное место, где применяются правила
произношения. Вызывается из ``PronunciationAwareTTSClient.synthesize`` ПОСЛЕ
``sanitize_text_for_speech_backend`` и ДО HTTP-запроса к провайдеру.

Стадии (применяются последовательно):
    1. SSML extract (опц., выкл по умолчанию) — strip ``<phoneme>``/``<sub alias>``.
    2. Нормализация — числа, даты, валюты, аббревиатуры (по локали).
    3. Regex-правила (precompiled, порядок из БД).
    4. Alias + stress-правила (Aho-Corasick, longest-match, word-boundary).
    5. Provider-final (silero_ru_latin_to_cyrillic и т.п.) — НЕ здесь;
       остаётся внутри LocalTTSEngine для litserve.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

import ahocorasick

from core.clients.tts_pronunciation.models import (
    CompiledPronunciation,
    _CompiledAliasRule,
    get_provider_capabilities,
)
from core.logging import get_logger
from core.utils.text_normalizers.normalizer import get_text_normalizer


logger = get_logger(__name__)

_WORD_BOUNDARY_LEFT = re.compile(r"(?<!\w)")
_WORD_BOUNDARY_RIGHT = re.compile(r"(?!\w)")

_WORD_SEP = re.compile(r"\W")


def _is_word_boundary_at(text: str, start: int, end: int) -> bool:
    """Проверяет, что вхождение [start:end] стоит на границах слова."""
    before_ok = (start == 0) or not text[start - 1].isalnum() and text[start - 1] != "_"
    after_ok = (end == len(text)) or not text[end].isalnum() and text[end] != "_"
    return before_ok and after_ok


def _apply_ssml_extract(text: str) -> str:
    """Минимальный SSML-стриппер: извлекает alias из ``<sub alias="...">`` и ``<phoneme>``.

    Только для провайдеров с поддержкой ``ssml_subset_enabled``. Остальные
    теги удаляются, их текстовое содержимое сохраняется.
    """
    try:
        root = ET.fromstring(f"<root>{text}</root>")
    except ET.ParseError:
        return text

    parts: list[str] = []

    def _walk(node: ET.Element) -> None:
        tag = node.tag.lower() if isinstance(node.tag, str) else ""
        if tag == "sub":
            alias = node.get("alias") or node.get("alias", "")
            parts.append(alias or (node.text or ""))
        elif tag == "phoneme":
            parts.append(node.text or "")
        else:
            if node.text:
                parts.append(node.text)
        for child in node:
            _walk(child)
            if child.tail:
                parts.append(child.tail)

    _walk(root)
    return "".join(parts)


def _build_automaton(
    rules: list[_CompiledAliasRule],
    *,
    provider: str,
    voice: Optional[str],
    language: Optional[str],
    capabilities_stress: bool,
    case_sensitive_subset: Optional[bool] = None,
) -> Optional[ahocorasick.Automaton]:
    """Строит Aho-Corasick automaton из применимых alias-правил.

    case_sensitive_subset:
        None — все правила;
        True — только ``case_sensitive``;
        False — только регистронезависимые.
    """
    automaton: ahocorasick.Automaton = ahocorasick.Automaton()
    added = 0

    for rule in rules:
        if case_sensitive_subset is not None and rule.case_sensitive != case_sensitive_subset:
            continue
        if not rule.enabled if hasattr(rule, "enabled") else False:
            continue
        if rule.is_stress and not capabilities_stress:
            continue
        if rule.providers is not None and provider not in rule.providers:
            continue
        if rule.voices is not None and voice not in rule.voices:
            continue
        if rule.language is not None and language is not None:
            if not language.startswith(rule.language):
                continue

        key = rule.pattern if rule.case_sensitive else rule.pattern.lower()
        automaton.add_word(key, rule)
        added += 1

    if added == 0:
        return None

    automaton.make_automaton()
    return automaton


def _apply_alias_rules_ac(
    text: str,
    automaton: ahocorasick.Automaton,
    *,
    lower_fold: bool,
) -> str:
    """Применяет Aho-Corasick замены с longest-match и word-boundary.

    lower_fold=False: совпадения и автомат по исходной строке (case-sensitive правила).
    lower_fold=True: сканируем ``text.lower()``, границы слова проверяем в исходном ``text``.

    Порядок: longest-match побеждает при перекрытии.
    """
    haystack = text.lower() if lower_fold else text
    matches: list[tuple[int, int, str]] = []

    for end_idx, rule in automaton.iter(haystack):
        pattern = rule.pattern.lower() if lower_fold else rule.pattern
        start_idx = end_idx - len(pattern) + 1
        if rule.word_boundary and not _is_word_boundary_at(text, start_idx, end_idx + 1):
            continue
        matches.append((start_idx, end_idx + 1, rule.replacement))

    if not matches:
        return text

    matches.sort(key=lambda m: (m[0], -(m[1] - m[0])))

    result: list[str] = []
    cursor = 0
    for start, end, replacement in matches:
        if start < cursor:
            continue
        result.append(text[cursor:start])
        result.append(replacement)
        cursor = end

    result.append(text[cursor:])
    return "".join(result)


class TtsTextPipeline:
    """Text-shaping pipeline для TTS.

    Экземпляр является stateless и может использоваться параллельно.
    Тяжёлые объекты (automaton) строятся при каждом ``transform`` из
    ``CompiledPronunciation``, поэтому сам pipeline не кешируется —
    кешируется ``CompiledPronunciation`` в ``voice_resolver``.
    """

    def transform(
        self,
        text: str,
        *,
        pronunciation: CompiledPronunciation,
        provider: str,
        voice: Optional[str] = None,
        language: Optional[str] = None,
    ) -> str:
        """Применяет все стадии text-shaping и возвращает преобразованный текст.

        Args:
            text: Входной текст (уже прошедший ``sanitize_text_for_speech_backend``).
            pronunciation: Скомпилированный набор правил.
            provider: Имя TTS-провайдера (влияет на фильтрацию правил).
            voice: Имя голоса (влияет на фильтрацию правил по ``voices``).
            language: Язык (BCP-47, используется для фильтрации по ``language``).
        """
        if not text:
            return text

        caps = get_provider_capabilities(provider)
        original_len = len(text)
        rules_applied = 0

        # Стадия 1: SSML extract (опционально)
        if pronunciation.ssml_subset_enabled:
            text = _apply_ssml_extract(text)

        # Стадия 2: Нормализация (числа, даты, валюты, аббревиатуры)
        if caps.normalization:
            normalizer = get_text_normalizer()
            text = normalizer.normalize(text, pronunciation.normalization)

        # Стадия 3: Regex-правила
        if caps.regex and pronunciation.regex_rules:
            for rule in pronunciation.regex_rules:
                if rule.providers is not None and provider not in rule.providers:
                    continue
                if rule.voices is not None and voice not in rule.voices:
                    continue
                if rule.language is not None and language is not None:
                    if not language.startswith(rule.language):
                        continue
                new_text = rule.pattern.sub(rule.replacement, text)
                if new_text != text:
                    rules_applied += 1
                    text = new_text

        # Стадии 4+5: Alias + stress (сначала case-sensitive, затем регистронезависимые)
        if caps.alias and pronunciation.alias_rules:
            alias_before = text
            auto_cs = _build_automaton(
                pronunciation.alias_rules,
                provider=provider,
                voice=voice,
                language=language,
                capabilities_stress=caps.stress_marker,
                case_sensitive_subset=True,
            )
            if auto_cs is not None:
                text = _apply_alias_rules_ac(text, auto_cs, lower_fold=False)
            auto_ci = _build_automaton(
                pronunciation.alias_rules,
                provider=provider,
                voice=voice,
                language=language,
                capabilities_stress=caps.stress_marker,
                case_sensitive_subset=False,
            )
            if auto_ci is not None:
                text = _apply_alias_rules_ac(text, auto_ci, lower_fold=True)
            if text != alias_before:
                rules_applied += 1

        if rules_applied > 0 or len(text) != original_len:
            logger.debug(
                "voice.tts.pronunciation.transform",
                provider=provider,
                voice=voice,
                language=language,
                original_len=original_len,
                transformed_len=len(text),
                rules_applied=rules_applied,
            )

        return text


_default_pipeline = TtsTextPipeline()


def get_tts_text_pipeline() -> TtsTextPipeline:
    return _default_pipeline


__all__ = ["TtsTextPipeline", "get_tts_text_pipeline"]
