"""Карта файлов корпуса example-docs → ожидаемое поведение FileReader.

CORPUS генерируется scripts/generate_corpus_manifest.py из GitHub tree + overrides.yaml.
Пути — относительно tests/core/files/example-docs/.

Правила:
- is_unsupported=True:  ожидаем FileReadError (зашифрованный/пустой/нечитаемый).
- uses_vision_llm=True: тест настраивает очередь MockLLM перед вызовом reader.read().
- uses_mock_stt_tier=True: reader.read() вызывается с transcription_company_id=corpus_tier_{unique_id}.
- skip_reason not None:  тест помечается pytest.skip (runtime-only, напр. HEIC без libheif).
- allows_empty_text=True: допускается pages[0].text == "" (файл пустой по замыслу).
"""

from __future__ import annotations

from tests.core.files.corpus.manifest_generated import CORPUS, READER_REMOTE_PATHS
from tests.core.files.corpus.models import (
    CORPUS_DIR,
    READER_CORPUS_PREFIX_EXCLUDE,
    CorpusFile,
)

POSITIVE = tuple(entry for entry in CORPUS if not entry.is_unsupported and entry.skip_reason is None)
NEGATIVE = tuple(entry for entry in CORPUS if entry.is_unsupported)
SKIPPED = tuple(entry for entry in CORPUS if entry.skip_reason is not None)
ALL_PATHS = frozenset(entry.relative_path for entry in CORPUS)

__all__ = [
    "ALL_PATHS",
    "CORPUS",
    "CORPUS_DIR",
    "CorpusFile",
    "NEGATIVE",
    "POSITIVE",
    "READER_CORPUS_PREFIX_EXCLUDE",
    "READER_REMOTE_PATHS",
    "SKIPPED",
]
