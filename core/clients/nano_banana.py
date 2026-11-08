"""Клиент генерации изображений: Google native generateContent для crop; LLM capability для остального."""

from __future__ import annotations

import base64
import re
from typing import Literal, Protocol

import httpx
from a2a.helpers.proto_helpers import get_message_text
from a2a.types import Message, Part, Role

from core.ai.models import ResolvedAIModel
from core.ai.providers import LINNEX_LLM_AUTO_MODEL, AICapability
from core.ai.requirements import AIRequestRequirements, AISelection
from core.ai.resolver import resolve_ai_model
from core.ai.runtime import create_llm_client_from_ai_model
from core.billing.service import BillingService
from core.clients.llm.messages import build_a2a_message
from core.config import get_settings
from core.config.llm_openai_compat import resolve_provider_api_key_for_openai_compatible_calls
from core.files.create_spec import FileSourceKind, FileSourceRef
from core.files.file_ref import stored_file_ref
from core.files.models import FileRecord
from core.files.object_store.gate import FileGate
from core.files.object_store.principals import SystemPrincipal
from core.files.reader.service import FileReader
from core.files.registry import build_file_create_spec
from core.logging import get_logger
from core.types import JsonObject, parse_json_object

logger = get_logger(__name__)

ImageEditMode = Literal["product_placement", "crop"]

_DEFAULT_CROP_MODEL = "google:gemini-3.1-flash-image"

_PRODUCT_PLACEMENT_EDIT_PREAMBLE = """CRITICAL: PHOTO EDITING TASK - ABSOLUTE PROHIBITION ON GENERATION

**YOU ARE FORBIDDEN FROM:**
- Generating a NEW person (different face, body, identity, gender)
- Creating a NEW background or scene
- Generating a NEW image from scratch

**YOU MUST:**
- EDIT the EXISTING BASE IMAGE (Image #1) ONLY
- PRESERVE the EXACT person, face, body, pose, background
- ADD the product to the EXISTING person in the BASE IMAGE"""

_GOOGLE_NATIVE_GENERATE_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


class _ChatLLM(Protocol):
    async def chat(
        self,
        messages: list[Message],
        *,
        extra_body: JsonObject | None = None,
    ) -> Message:
        ...


def _selection_from_nano_banana_model(model_cfg: str) -> AISelection | None:
    stripped = model_cfg.strip()
    if stripped == "" or stripped == LINNEX_LLM_AUTO_MODEL:
        return None
    if ":" not in stripped:
        raise ValueError(
            "nano_banana.model must be 'auto' or 'provider:model', "
            + f"got {model_cfg!r}"
        )
    provider, model = stripped.split(":", 1)
    provider = provider.strip()
    model = model.strip()
    if provider == "" or model == "":
        raise ValueError(
            "nano_banana.model must be 'auto' or 'provider:model', "
            + f"got {model_cfg!r}"
        )
    return AISelection(provider=provider, model=model)


def _crop_google_model() -> str:
    """Модель native generateContent для image crop (без LLM/OpenAI-compat фолбека)."""
    configured = get_settings().nano_banana.model.strip()
    raw = configured if configured and configured != LINNEX_LLM_AUTO_MODEL else _DEFAULT_CROP_MODEL
    selection = _selection_from_nano_banana_model(raw)
    if selection is None or selection.provider != "google" or selection.model is None:
        raise ValueError(
            "image crop requires nano_banana.model like "
            + f"{_DEFAULT_CROP_MODEL!r}, got {configured!r}"
        )
    return selection.model.strip()


def _image_gen_requirements() -> AIRequestRequirements:
    return AIRequestRequirements(
        vision_required=True,
        image_output_required=True,
    )


class NanoBananaClient:
    """
    Клиент для генерации изображений через platform LLM capability.

    ``editing_mode=crop`` — только Google native ``generateContent``; текст запроса
    целиком задаёт caller (доменные промпты меню/студии в клиент не входят).
    """

    def __init__(self, billing_service: BillingService) -> None:
        self._billing_service: BillingService = billing_service
        self._llm: _ChatLLM | None = None
        self._resolved: ResolvedAIModel | None = None

    def _resolve_image_model(self) -> ResolvedAIModel:
        if self._resolved is not None:
            return self._resolved
        selection = _selection_from_nano_banana_model(get_settings().nano_banana.model)
        resolved = resolve_ai_model(
            AICapability.IMAGE_GEN,
            requirements=_image_gen_requirements(),
            selection=selection,
            include_platform_default=True,
        )
        if resolved is None:
            raise ValueError(
                "NanoBananaClient: platform default for capability=image_gen is not configured"
            )
        self._resolved = resolved
        return resolved

    def _create_image_generation_client(self) -> _ChatLLM:
        """Resolve and cache the image generation LLM client (non-crop paths)."""
        if self._llm is None:
            self._llm = create_llm_client_from_ai_model(
                self._resolve_image_model(),
                billing_service=self._billing_service,
            )
        return self._llm

    async def generate_images(
        self,
        prompt: str,
        reference_file_ids: list[str] | None = None,
        num_images: int = 1,
        is_editing: bool = False,
        editing_mode: ImageEditMode = "product_placement",
    ) -> list[str]:
        """
        Генерирует изображения.

        ``editing_mode=crop`` — только Google native generateContent
        (``nano_banana.model``, по умолчанию gemini-3.1-flash-image); prompt caller'а
        уходит как есть.
        """
        logger.info(
            "image.generate.started",
            num_images=num_images,
            editing_mode=editing_mode if is_editing else "generate",
            prompt_preview=prompt[:50],
        )

        if is_editing and editing_mode == "crop":
            return await self._generate_via_google_native(
                prompt=prompt,
                reference_file_ids=reference_file_ids,
                is_editing=True,
                editing_mode="crop",
                model=_crop_google_model(),
            )

        parts: list[Part] = []

        if is_editing and reference_file_ids:
            parts.append(Part(text=_PRODUCT_PLACEMENT_EDIT_PREAMBLE))

        if reference_file_ids:
            logger.info("image.generate.references", count=len(reference_file_ids))

            for idx, file_id in enumerate(reference_file_ids):
                file_record = await FileRecord.get(file_id)

                if file_record is None:
                    raise ValueError(f"NanoBananaClient: reference file not found: {file_id}")

                if file_record.company_id is None or file_record.company_id == "":
                    raise ValueError(
                        f"NanoBananaClient: reference file missing company_id: {file_id}"
                    )
                handle = await FileGate().open_record(
                    file_record,
                    SystemPrincipal(company_id=file_record.company_id),
                )
                file_bytes = await handle.read_bytes()

                if not file_bytes:
                    raise ValueError(f"NanoBananaClient: reference file empty: {file_id}")

                if is_editing and idx == 0:
                    parts.append(
                        Part(
                            text="""BASE IMAGE TO EDIT (Image #1) - DO NOT GENERATE NEW IMAGE

**THIS IS THE EXISTING PHOTOGRAPH - YOU MUST EDIT IT, NOT REPLACE IT**"""
                        )
                    )

                parts.append(
                    Part(
                        raw=file_bytes,
                        media_type=file_record.content_type,
                        filename=file_id,
                    )
                )
                logger.info("image.generate.reference_added", file_id=file_id, index=idx)

        parts.append(Part(text=prompt))

        llm = self._create_image_generation_client()

        llm_response: Message = await llm.chat(
            [
                build_a2a_message(
                    role=Role.ROLE_USER,
                    parts=parts,
                )
            ],
            extra_body={"modalities": ["image", "text"]},
        )

        file_pattern: re.Pattern[str] = re.compile(r"file_([a-f0-9]{12})")
        file_ids: list[str] = []
        for file_match in file_pattern.finditer(get_message_text(llm_response)):
            file_ids.append(f"file_{file_match.group(1)}")

        if not file_ids:
            raise RuntimeError("NanoBananaClient: LLM response contained no file_id")

        logger.info("image.generate.completed", file_ids=file_ids, count=len(file_ids))
        return file_ids

    async def _generate_via_google_native(
        self,
        *,
        prompt: str,
        reference_file_ids: list[str] | None,
        is_editing: bool,
        editing_mode: ImageEditMode,
        model: str,
    ) -> list[str]:
        """Gemini image: native generateContent; текст — только ``prompt`` caller'а."""
        _ = is_editing
        if model.strip() == "":
            raise ValueError("NanoBananaClient: google image model is empty")
        if not reference_file_ids:
            raise ValueError("NanoBananaClient: crop requires reference_file_ids")
        if prompt.strip() == "":
            raise ValueError("NanoBananaClient: crop requires a non-empty prompt")

        parts_payload: list[JsonObject] = [{"text": prompt.strip()}]
        source_file_id = reference_file_ids[0]
        logger.info("image.generate.references", count=len(reference_file_ids))
        for file_id in reference_file_ids:
            file_record = await FileRecord.get(file_id)
            if file_record is None:
                raise ValueError(f"NanoBananaClient: reference file not found: {file_id}")
            if file_record.company_id is None or file_record.company_id == "":
                raise ValueError(
                    f"NanoBananaClient: reference file missing company_id: {file_id}"
                )
            handle = await FileGate().open_record(
                file_record,
                SystemPrincipal(company_id=file_record.company_id),
            )
            file_bytes = await handle.read_bytes()
            if not file_bytes:
                raise ValueError(f"NanoBananaClient: reference file empty: {file_id}")
            media_type = file_record.content_type.strip()
            if media_type == "":
                media_type = "image/png"
            parts_payload.append(
                {
                    "inline_data": {
                        "mime_type": media_type,
                        "data": base64.b64encode(file_bytes).decode("ascii"),
                    }
                }
            )
            source_file_id = file_id
            logger.info("image.generate.reference_added", file_id=file_id)

        api_key = resolve_provider_api_key_for_openai_compatible_calls(
            get_settings().llm,
            "google",
        )
        timeout_s = float(get_settings().nano_banana.timeout)
        url = _GOOGLE_NATIVE_GENERATE_URL.format(model=model.strip())
        body: JsonObject = {
            "contents": [{"role": "user", "parts": parts_payload}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                http_response = await client.post(
                    url,
                    params={"key": api_key},
                    json=body,
                )
                _ = http_response.raise_for_status()
                payload = parse_json_object(
                    http_response.content,
                    "nano_banana.google.generateContent",
                )
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"NanoBananaClient google generateContent failed: {exc}"
            ) from exc

        image_bytes: bytes | None = None
        content_type = "image/png"
        candidates = payload.get("candidates")
        if isinstance(candidates, list):
            for candidate_raw in candidates:
                if not isinstance(candidate_raw, dict):
                    continue
                content_raw = candidate_raw.get("content")
                if not isinstance(content_raw, dict):
                    continue
                parts_raw = content_raw.get("parts")
                if not isinstance(parts_raw, list):
                    continue
                for part_raw in parts_raw:
                    if not isinstance(part_raw, dict):
                        continue
                    inline = part_raw.get("inlineData")
                    if inline is None:
                        inline = part_raw.get("inline_data")
                    if not isinstance(inline, dict):
                        continue
                    data_b64 = inline.get("data")
                    if not isinstance(data_b64, str) or data_b64.strip() == "":
                        continue
                    image_bytes = base64.b64decode(data_b64)
                    mime = inline.get("mimeType")
                    if not isinstance(mime, str) or mime.strip() == "":
                        mime = inline.get("mime_type")
                    if isinstance(mime, str) and mime.strip() != "":
                        content_type = mime.strip()
                    break
                if image_bytes is not None:
                    break

        if image_bytes is None:
            raise RuntimeError(
                "NanoBananaClient: generateContent returned no image "
                + f"(model={model!r})"
            )

        files_service = FileReader.require_files_service()
        extension = "png" if "png" in content_type else "jpg"
        original_name = f"nano-banana-{editing_mode}.{extension}"
        spec = build_file_create_spec(
            source_kind=FileSourceKind.GENERATED_EPHEMERAL,
            source_ref=FileSourceRef(entity_id=source_file_id),
            metadata={
                "nano_banana": True,
                "editing_mode": editing_mode,
                "provider": "google",
                "model": model,
            },
        )
        created = await files_service.create(
            spec,
            image_bytes,
            original_name=original_name,
            content_type=content_type,
        )
        ref = stored_file_ref(created)
        if ref.file_id is None or not ref.file_id.strip():
            raise ValueError("NanoBananaClient: persist returned empty file_id")
        file_ids = [ref.file_id.strip()]
        logger.info("image.generate.completed", file_ids=file_ids, count=len(file_ids))
        return file_ids


class NanoBananaClientFactory:
    """Фабрика для создания Nano Banana клиентов"""

    @staticmethod
    def create_client(*, billing_service: BillingService) -> NanoBananaClient:
        """Создает клиент на основе конфигурации"""
        settings = get_settings()

        if not settings.nano_banana.enabled:
            raise ValueError("Nano Banana is not configured")

        return NanoBananaClient(billing_service)
