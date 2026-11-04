"""Spike: pymupdf4llm==1.28.x на 3.14t / pymupdf<2 — parse quality, не nested delivery.

Не в sync read_file hot path. Наблюдение spike: пакет ставится и `to_markdown(path)`
не падает; для born-digital PDF с insert_text/insert_image ответ может быть
пустым markdown (`\\n\\n`) — поэтому nested delivery остаётся нашим extract→md+Parts.
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import pytest

from tests.core.files.golden.bytes import pdf_text_and_embedded_image

_MARKER = "SPIKE_PDF4LLM"


@pytest.mark.timeout(120)
def test_pymupdf4llm_optional_spike_runs() -> None:
    if importlib.util.find_spec("pymupdf4llm") is None:
        pytest.skip("pymupdf4llm not installed — spike only")
    import pymupdf4llm

    raw = pdf_text_and_embedded_image(_MARKER)
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "spike.pdf"
        path.write_bytes(raw)
        markdown = pymupdf4llm.to_markdown(str(path), embed_images=False)
    assert isinstance(markdown, str)
    # Качество не гарантируем: пустой md — допустимый результат spike.
    _ = _MARKER
