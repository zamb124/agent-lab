"""Модели корпуса example-docs для FileReader-тестов."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.files.reader.models import FileReadKind

CORPUS_DIR = Path(__file__).parent.parent / "example-docs"

READER_CORPUS_PREFIX_EXCLUDE = ("test_evaluate_files/",)


@dataclass(frozen=True)
class CorpusFile:
    relative_path: str
    expected_kind: FileReadKind
    expected_text_substring: str | None = None
    expected_min_pages: int = 1
    is_unsupported: bool = False
    uses_vision_llm: bool = False
    uses_mock_stt_tier: bool = False
    allows_empty_text: bool = False
    skip_reason: str | None = None

    @property
    def path(self) -> Path:
        return CORPUS_DIR / self.relative_path
