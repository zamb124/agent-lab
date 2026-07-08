"""Параметризованные тесты FileReader на корпусе unstructured/example-docs.

Полный путь reader.read() — никаких patchy внутренних функций.
Единственные внешние замены:
  - LLM/Vision: core.ai.runtime возвращает MockLLM в TESTING.
    Для vision-файлов тест настраивает очередь MockLLM на "MOCK_VISION".
  - STT: передаётся transcription_company_id без записи в company_voice_providers
    → tier резолвится в mock STT-провайдер из конфигурации тестового окружения.
"""

from __future__ import annotations

import pytest

from core.files.checksum import compute_content_checksum_sha256
from core.files.reader import FileReader
from core.files.reader.models import FileReadKind, ReadFileArgs
from tests.core.files.corpus.helpers import corpus_stt_company_id, require_heic_entry_supported
from tests.core.files.corpus.manifest import CORPUS, CorpusFile

_MOCK_VISION_TEXT = "MOCK_VISION"


def _is_vision(entry: CorpusFile) -> bool:
    return entry.uses_vision_llm


def _is_audio(entry: CorpusFile) -> bool:
    return entry.uses_mock_stt_tier


# ---------------------------------------------------------------------------
# Позитивные тесты
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entry",
    [e for e in CORPUS if not e.is_unsupported],
    ids=lambda e: e.relative_path,
)
@pytest.mark.timeout(180)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_corpus_file_reads_correctly(
    entry: CorpusFile,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    """Для каждого файла: правильный kind + ненулевой текст + чексумма стабильна."""
    if entry.skip_reason:
        pytest.skip(entry.skip_reason)
    require_heic_entry_supported(entry.relative_path)

    if not entry.path.exists():
        pytest.skip(f"Файл отсутствует в корпусе: {entry.relative_path}")

    # Vision: настраиваем очередь MockLLM так, чтобы вернуть MOCK_VISION
    if _is_vision(entry):
        mock_llm_with_queue([_MOCK_VISION_TEXT])

    raw = entry.path.read_bytes()
    reader = FileReader()

    # 1) recognize_file_type по расширению/head (exotic suffixes могут остаться UNKNOWN)
    info = reader.recognize_file_type(file_name=entry.path.name, head=raw[:8192])
    if info.detected_kind != FileReadKind.UNKNOWN:
        assert info.detected_kind == entry.expected_kind, (
            f"{entry.relative_path}: recognize_file_type дал {info.detected_kind!r}, "
            f"ожидали {entry.expected_kind!r}"
        )

    # 2) полное чтение
    transcription_company_id: str | None = None
    vision_prompt: str | None = None
    if _is_audio(entry):
        transcription_company_id = corpus_stt_company_id(unique_id)
    if _is_vision(entry):
        vision_prompt = "Опиши содержимое изображения."

    read_args = ReadFileArgs(
        page_end=-1,
        vision_prompt=vision_prompt or "",
        transcription_company_id=transcription_company_id,
    )
    extract = await reader.read(
        raw,
        read_args,
        file_name=entry.path.name,
    )

    # 3) kind совпадает
    assert extract.kind == entry.expected_kind, (
        f"{entry.relative_path}: kind={extract.kind!r}, "
        f"expected={entry.expected_kind!r}"
    )

    # 4) page_count инвариант
    pages_total = extract.page_layout.pages_total
    assert pages_total == len(extract.pages), (
        f"{entry.relative_path}: pages_total={pages_total} != len(pages)={len(extract.pages)}"
    )
    assert pages_total >= entry.expected_min_pages, (
        f"{entry.relative_path}: pages_total={pages_total} < {entry.expected_min_pages}"
    )

    # 5) текст ненулевой (если файл не разрешён быть пустым)
    joined_text = "\n".join(p.text for p in extract.pages)
    if not entry.allows_empty_text:
        assert len(joined_text.strip()) > 0, (
            f"{entry.relative_path}: extracted text is empty (pages={pages_total})"
        )

    # 6) конкретная подстрока
    if entry.expected_text_substring:
        assert entry.expected_text_substring in joined_text, (
            f"{entry.relative_path}: подстрока {entry.expected_text_substring!r} "
            f"не найдена в тексте (первые 200 сим): {joined_text[:200]!r}"
        )

    # 7) чексумма
    assert extract.source_checksum == compute_content_checksum_sha256(raw), (
        f"{entry.relative_path}: source_checksum не совпадает с sha256 исходных байт"
    )
