"""Обёртка NanoBananaClient поверх универсального ``ImageGenClient``.

Контракт ``generate_images(prompt, reference_file_ids, num_images, is_editing,
editing_mode)`` сохранён для существующих вызовов: ``editing_mode=crop`` —
google native generateContent; остальное — chat-транспорт LLM capability
с ``modalities``. Новый код должен вызывать
``core.clients.image_gen.ImageGenClient`` напрямую.
"""

from __future__ import annotations

from typing import Literal

from core.ai.providers import LINNEX_LLM_AUTO_MODEL
from core.ai.requirements import AISelection
from core.billing.service import BillingService
from core.clients.image_gen import ImageGenClient, ImageGenSpec
from core.config import get_settings
from core.logging import get_logger

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

_BASE_IMAGE_LABEL = """BASE IMAGE TO EDIT (Image #1) - DO NOT GENERATE NEW IMAGE

**THIS IS THE EXISTING PHOTOGRAPH - YOU MUST EDIT IT, NOT REPLACE IT**"""


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


def _crop_selection() -> AISelection:
    """Explicit google-selection для crop (nano_banana.model или default)."""
    configured = get_settings().nano_banana.model.strip()
    raw = configured if configured and configured != LINNEX_LLM_AUTO_MODEL else _DEFAULT_CROP_MODEL
    selection = _selection_from_nano_banana_model(raw)
    if selection is None or selection.provider != "google" or selection.model is None:
        raise ValueError(
            "image crop requires nano_banana.model like "
            + f"{_DEFAULT_CROP_MODEL!r}, got {configured!r}"
        )
    return AISelection(provider="google", model=selection.model.strip())


class NanoBananaClient:
    """
    Клиент для генерации изображений через platform LLM capability.

    ``editing_mode=crop`` — только Google native ``generateContent``; текст запроса
    целиком задаёт caller (доменные промпты меню/студии в клиент не входят).
    """

    def __init__(self, billing_service: BillingService) -> None:
        self._billing_service: BillingService = billing_service

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
        _ = num_images
        logger.info(
            "image.generate.started",
            num_images=num_images,
            editing_mode=editing_mode if is_editing else "generate",
            prompt_preview=prompt[:50],
        )

        if is_editing and editing_mode == "crop":
            if not reference_file_ids:
                raise ValueError("NanoBananaClient: crop requires reference_file_ids")
            client = ImageGenClient(
                self._billing_service,
                selection=_crop_selection(),
            )
            result = await client.edit(
                ImageGenSpec(
                    prompt=prompt,
                    references=tuple(reference_file_ids),
                    transport="google_native",
                )
            )
            return result.file_ids

        parts_prompt = prompt
        if is_editing and reference_file_ids:
            parts_prompt = (
                _PRODUCT_PLACEMENT_EDIT_PREAMBLE
                + "\n\n"
                + _BASE_IMAGE_LABEL
                + "\n\n"
                + prompt
            )

        client = ImageGenClient(
            self._billing_service,
            selection=_selection_from_nano_banana_model(get_settings().nano_banana.model),
        )
        spec = ImageGenSpec(
            prompt=parts_prompt,
            references=tuple(reference_file_ids or ()),
            transport="openai_chat",
        )
        result = (
            await client.edit(spec)
            if spec.references
            else await client.generate(spec)
        )
        return result.file_ids


class NanoBananaClientFactory:
    """Фабрика для создания Nano Banana клиентов"""

    @staticmethod
    def create_client(*, billing_service: BillingService) -> NanoBananaClient:
        """Создает клиент на основе конфигурации"""
        settings = get_settings()

        if not settings.nano_banana.enabled:
            raise ValueError("Nano Banana is not configured")

        return NanoBananaClient(billing_service)
