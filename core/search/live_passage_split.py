"""Fast in-memory heading-split for live-fetch pages (§4.5.2).

Splits markdown from FetchedPage into EvidencePassage list:
  1. Heading-split (H1–H3) via MarkdownHeadingParser.
  2. Token-cap: sections longer than max_passage_tokens are sub-split by word count.
  3. Optional focus_hint: boost passages from matching section_title.

All operations are in-memory; nothing is persisted to vector_documents.
"""

from __future__ import annotations

import re

from core.search.live_fetch import EvidencePassage, FetchedPage
from core.search.markdown_headings import parse_sections

_RE_WORDS = re.compile(r"\S+")

_DEFAULT_MAX_PASSAGE_TOKENS = 400
_DEFAULT_MAX_PASSAGES_PER_URL = 40


def _split_by_word_cap(text: str, cap: int) -> list[str]:
    """Sub-split a text blob into chunks of at most `cap` words."""
    words = _RE_WORDS.findall(text)
    if not words:
        return []
    chunks: list[str] = []
    for i in range(0, len(words), cap):
        chunks.append(" ".join(words[i : i + cap]))
    return chunks


def split_page_to_passages(
    page: FetchedPage,
    *,
    max_passage_tokens: int = _DEFAULT_MAX_PASSAGE_TOKENS,
    max_passages_per_url: int = _DEFAULT_MAX_PASSAGES_PER_URL,
    focus_hint: str | None = None,
) -> list[EvidencePassage]:
    """Split a FetchedPage into EvidencePassage list.

    Parameters
    ----------
    page:
        Live-fetched page; must have ``page.ok == True``.
    max_passage_tokens:
        Word-cap per passage (proxy for tokens).
    max_passages_per_url:
        Hard cap on total passages returned for this page.
    focus_hint:
        Optional section_title from the pointer index hit; passages whose
        section_title contains the hint are prepended (routing hint from §4.5.2).
    """
    if not page.ok or not page.markdown.strip():
        return []

    raw_sections = parse_sections(page.markdown, max_section_tokens=0)
    passages: list[EvidencePassage] = []
    char_cursor = 0

    for section in raw_sections:
        body = section.text if section.text else ""
        words = _RE_WORDS.findall(body)
        if not words:
            sub_texts: list[str] = [""]
        elif len(words) <= max_passage_tokens:
            sub_texts = [" ".join(words)]
        else:
            sub_texts = _split_by_word_cap(body, max_passage_tokens)

        for sub in sub_texts:
            passages.append(
                EvidencePassage(
                    source_url=page.source_url,
                    heading_trail=list(section.heading_trail),
                    section_title=section.section_title,
                    text=sub,
                    rerank_score=None,
                    char_start=char_cursor,
                )
            )
            char_cursor += len(sub) + 1

    if not passages:
        return []

    # Promote focus-hint passages to front for better rerank recall
    if focus_hint and focus_hint.strip():
        hint_lower = focus_hint.strip().lower()
        focused: list[EvidencePassage] = []
        rest: list[EvidencePassage] = []
        for p in passages:
            if hint_lower in p.section_title.lower() or hint_lower in " ".join(
                p.heading_trail
            ).lower():
                focused.append(p)
            else:
                rest.append(p)
        passages = focused + rest

    return passages[:max_passages_per_url]


def split_pages_to_passages(
    pages: list[FetchedPage],
    *,
    max_passage_tokens: int = _DEFAULT_MAX_PASSAGE_TOKENS,
    max_passages_per_url: int = _DEFAULT_MAX_PASSAGES_PER_URL,
    max_passages_total: int = 200,
    focus_hints: dict[str, str] | None = None,
) -> list[EvidencePassage]:
    """Split multiple pages; respect global cap max_passages_total.

    Parameters
    ----------
    focus_hints:
        Mapping ``{canonical_url: section_title}`` from pointer-index hits.
    """
    all_passages: list[EvidencePassage] = []
    for page in pages:
        hint = (focus_hints or {}).get(page.canonical_url) or (focus_hints or {}).get(
            page.source_url
        )
        page_passages = split_page_to_passages(
            page,
            max_passage_tokens=max_passage_tokens,
            max_passages_per_url=max_passages_per_url,
            focus_hint=hint,
        )
        all_passages.extend(page_passages)
        if len(all_passages) >= max_passages_total:
            break

    return all_passages[:max_passages_total]
