"""Salient terms extractor for pointer-index (§4.2).

Layers (priority order):
  1. Regex — CVE, versions, error codes, acronyms
  2. Structure — H1/H2/H3 heading tokens
  3. Statistical — KeyBERT via litserve (multilingual RU/EN) or local TF fallback

Prose is not persisted; terms live in metadata.salient_terms[].
"""

from __future__ import annotations

import re
from collections import Counter

_STOPWORDS_RU: frozenset[str] = frozenset(
    [
        "и", "в", "на", "с", "по", "для", "от", "к", "из", "за", "при", "до",
        "или", "не", "но", "а", "да", "то", "как", "так", "что", "это", "его",
        "её", "их", "он", "она", "они", "мы", "вы", "я", "ты", "все", "уже",
        "еще", "ещё", "тоже", "также", "может", "нет", "есть", "был", "была",
        "были", "будет", "быть", "о", "об", "со", "во", "ли", "бы", "же",
        "который", "которая", "которые", "которого", "которую", "которое",
        "под", "над", "без", "через", "между", "после", "перед",
        "когда", "если", "чтобы", "хотя", "потому", "поэтому", "однако",
    ]
)

_STOPWORDS_EN: frozenset[str] = frozenset(
    [
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "that", "this", "it", "its", "as", "not", "we", "you", "he", "she",
        "they", "our", "your", "their", "have", "has", "had", "will", "would",
        "can", "could", "should", "may", "might", "do", "does", "did", "all",
        "also", "so", "if", "when", "which", "who", "how", "up", "out", "more",
        "about", "then", "than", "use", "used", "using", "new", "two", "one",
        "get", "just", "like", "into", "only", "other", "some", "very",
    ]
)

_STOPWORDS: frozenset[str] = _STOPWORDS_RU | _STOPWORDS_EN

_RE_CVE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE)
_RE_GHSA = re.compile(r"\bGHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}\b", re.IGNORECASE)
_RE_VERSION = re.compile(r"\bv?\d+\.\d+(?:\.\d+)*(?:[-+][a-zA-Z0-9.+\-]+)?\b")
_RE_HEX_CODE = re.compile(r"\b0x[0-9A-Fa-f]{4,8}\b")
_RE_ERROR_CODE = re.compile(r"\b[A-Z][A-Z0-9_]{3,}(?:Error|Exception|Code|ID)?\b")
_RE_HEADING = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)
_RE_WORD = re.compile(r"\b[a-zA-Zа-яёА-ЯЁ][a-zA-Zа-яёА-ЯЁ0-9_\-]{2,}\b")
_RE_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_RE_MARKDOWN_NOISE = re.compile(r"[#*`>|]")


def _add_term(terms: list[str], seen: set[str], term: str) -> None:
    normalized = term.strip()
    if not normalized:
        return
    key = normalized.lower()
    if key not in seen:
        seen.add(key)
        terms.append(normalized)


def extract_priority_terms(markdown: str) -> list[str]:
    """Regex + heading layers (sync, always applied before KeyBERT/local TF)."""
    seen: set[str] = set()
    terms: list[str] = []

    for pattern in (_RE_CVE, _RE_GHSA, _RE_VERSION, _RE_HEX_CODE, _RE_ERROR_CODE):
        for match in pattern.finditer(markdown):
            _add_term(terms, seen, match.group(0))

    for match in _RE_HEADING.finditer(markdown):
        heading_text = match.group(1).strip()
        for word_match in _RE_WORD.finditer(heading_text):
            word = word_match.group(0)
            if word.lower() not in _STOPWORDS and len(word) >= 3:
                _add_term(terms, seen, word)

    return terms


def extract_local_statistical_terms(markdown: str, *, max_terms: int) -> list[str]:
    """Local TF fallback when KeyBERT is unavailable."""
    plain = _RE_MARKDOWN_LINK.sub(r"\1", markdown)
    plain = _RE_MARKDOWN_NOISE.sub(" ", plain)
    word_counts: Counter[str] = Counter()
    first_occurrence: dict[str, str] = {}
    for word_match in _RE_WORD.finditer(plain):
        word = word_match.group(0)
        key = word.lower()
        if key not in _STOPWORDS and len(word) >= 3:
            word_counts[key] += 1
            if key not in first_occurrence:
                first_occurrence[key] = word

    terms: list[str] = []
    seen: set[str] = set()
    for word_lower, _ in word_counts.most_common(max_terms):
        word = first_occurrence.get(word_lower, word_lower)
        _add_term(terms, seen, word)
    return terms


def merge_salient_terms(
    *,
    priority_terms: list[str],
    statistical_terms: list[str],
    max_terms: int,
) -> list[str]:
    """Merge priority + statistical layers preserving order and deduping."""
    seen: set[str] = set()
    merged: list[str] = []
    for term in [*priority_terms, *statistical_terms]:
        key = term.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(term.strip())
        if len(merged) >= max_terms:
            break
    return merged


def extract_salient_terms_local(markdown: str, *, max_terms: int = 80) -> list[str]:
    """Fully local extraction (regex + headings + TF). Used in tests and fallback."""
    priority = extract_priority_terms(markdown)
    statistical = extract_local_statistical_terms(
        markdown,
        max_terms=max(max_terms - len(priority), 0),
    )
    return merge_salient_terms(
        priority_terms=priority,
        statistical_terms=statistical,
        max_terms=max_terms,
    )


def extract_salient_terms(markdown: str, *, max_terms: int = 80) -> list[str]:
    """Sync local alias (backward-compatible for index_study unit tests)."""
    return extract_salient_terms_local(markdown, max_terms=max_terms)


def markdown_plain_for_keybert(markdown: str) -> str:
    """Light markdown cleanup before KeyBERT (mixed RU/EN)."""
    text = _RE_MARKDOWN_LINK.sub(r"\1", markdown)
    text = _RE_MARKDOWN_NOISE.sub(" ", text)
    return " ".join(text.split())
