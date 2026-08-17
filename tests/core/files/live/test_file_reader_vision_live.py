"""Live vision FileReader: печатный маркер в PNG и scanned PDF, без MockLLM."""

from __future__ import annotations

import pytest

from apps.frontend.container import FrontendContainer
from core.ai.providers import AICapability
from core.ai.requirements import AIRequestRequirements
from core.ai.resolver import resolve_ai_model
from core.files.reader.models import FileReadKind, ReadLane
from tests.core.clients.live_llm_provider_helpers import (
    disable_testing_mode,
    provider_api_key_configured,
)
from tests.core.files.golden.bytes import pdf_printed_page, png_with_text
from tests.core.files.golden.store import (
    configure_file_reader_persist,
    read_stored_extract,
    store_golden_file,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.network,
    pytest.mark.timeout(120),
    pytest.mark.usefixtures("file_reader_billing_service"),
]

_VISION_REQUIREMENTS = AIRequestRequirements(
    vision_required=True,
    required_input_modalities=("image",),
)


def _require_live_vision() -> None:
    resolved = resolve_ai_model(
        AICapability.LLM_VISION,
        requirements=_VISION_REQUIREMENTS,
        include_platform_default=True,
    )
    if resolved is None:
        pytest.skip("llm_vision не настроен")
    provider = resolved.provider
    if provider is None or not provider.strip():
        pytest.skip("llm_vision: provider пуст")
    if not provider_api_key_configured(provider):
        pytest.skip(f"llm_vision: api_key не настроен для {provider}")
    record = resolved.model_record
    if record is None or not record.supports_vision:
        pytest.skip("llm_vision: нет модели с input_modalities=image")


async def test_live_vision_png_prints_marker(
    frontend_container: FrontendContainer,
    unique_id: str,
) -> None:
    token = f"LIVE_OCR_{unique_id}"
    with disable_testing_mode():
        _require_live_vision()
    configure_file_reader_persist(frontend_container.files_service)
    raw = png_with_text(token, width=1200, height=400)
    file_ref = await store_golden_file(
        frontend_container.files_service,
        raw=raw,
        original_name=f"live_ocr_{unique_id}.png",
    )
    with disable_testing_mode():
        _require_live_vision()
        extract = await read_stored_extract(file_ref)
    assert extract.kind == FileReadKind.IMAGE
    assert extract.read_lane == ReadLane.VISION
    assert token in extract.canonical_text()


async def test_live_vision_scanned_pdf_prints_marker(
    frontend_container: FrontendContainer,
    unique_id: str,
) -> None:
    token = f"LIVE_OCR_{unique_id}"
    with disable_testing_mode():
        _require_live_vision()
    configure_file_reader_persist(frontend_container.files_service)
    raw = pdf_printed_page(token, width=1200, height=400)
    file_ref = await store_golden_file(
        frontend_container.files_service,
        raw=raw,
        original_name=f"live_ocr_{unique_id}.pdf",
    )
    with disable_testing_mode():
        _require_live_vision()
        extract = await read_stored_extract(file_ref)
    assert extract.kind == FileReadKind.PDF
    assert extract.read_lane == ReadLane.HYBRID
    assert token in extract.canonical_text()
