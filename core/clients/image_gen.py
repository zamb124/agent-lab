"""Универсальный клиент генерации/редактирования изображений поверх core.ai.

``generate`` резолвит ``AICapability.IMAGE_GEN``, ``edit`` —
``AICapability.IMAGE_EDIT`` (image input + image output в каталоге).

Контракт — ``ImageGenSpec`` (union-параметры разных image API: prompt, references,
geometry, формат, seed/mask). Клиент резолвит модель через ``core.ai.resolver``,
выбирает транспорт по провайдеру и валидирует set-параметры по таблице
``_TRANSPORT_SUPPORTED_PARAMETERS``: неподдерживаемый параметр — явная ошибка,
молчаливого дропа нет.

Транспорты:

- ``google_native`` — ``POST {model}:generateContent`` (Nano Banana API):
  ``generationConfig.imageConfig`` = aspectRatio/imageSize, refs — ``inline_data``.
- ``openai_chat`` — ``LLMClient.chat`` с ``extra_body.modalities`` и
  ``extra_body.image_config`` (OpenRouter-совместимая проекция).
"""

from __future__ import annotations

import base64
import re
from io import BytesIO
from typing import ClassVar, Literal, Protocol

import httpx
from a2a.helpers.proto_helpers import get_message_text
from a2a.types import Message, Part, Role
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.ai.models import ResolvedAIModel
from core.ai.providers import AICapability
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
from core.models.base import StrictBaseModel
from core.types import JsonObject, parse_json_object

logger = get_logger(__name__)

ImageGenTransport = Literal["google_native", "openai_chat"]

_IMAGE_GEN_MAX_REFERENCES = 14

_GOOGLE_NATIVE_GENERATE_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

_FILE_ID_RE: re.Pattern[str] = re.compile(r"file_([a-f0-9]{12})")

_OUTPUT_FORMAT_CONTENT_TYPE: dict[str, str] = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}

# Set-параметры ImageGenSpec, которые транспорт умеет честно исполнить.
# Параметр вне таблицы — unsupported_parameter, а не молчаливый дроп.
_TRANSPORT_SUPPORTED_PARAMETERS: dict[ImageGenTransport, frozenset[str]] = {
    "google_native": frozenset(
        {"count", "aspect_ratio", "image_size", "output_format"}
    ),
    "openai_chat": frozenset({"aspect_ratio", "image_size"}),
}


class ImageGenReference(StrictBaseModel):
    """Референс для edit: file_id источника; ``page`` растризует страницу PDF."""

    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True)

    file_id: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=0)


class ImageGenSpec(StrictBaseModel):
    """Канонический запрос image gen: prompt + references + параметры выхода."""

    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True)

    prompt: str = Field(min_length=1)
    references: tuple[str, ...] = ()
    count: int = Field(default=1, ge=1, le=4)
    aspect_ratio: str | None = None
    image_size: Literal["1K", "2K", "4K"] | None = None
    output_format: Literal["png", "jpeg", "webp"] | None = None
    mask_file_id: str | None = None
    seed: int | None = None
    negative_prompt: str | None = None
    transport: Literal["auto", "google_native", "openai_chat"] = "auto"

    @model_validator(mode="after")
    def _check_references(self) -> ImageGenSpec:
        if any(ref.strip() == "" for ref in self.references):
            raise ValueError("references must be non-empty file_id strings")
        return self


class ImageGenResult(StrictBaseModel):
    """file_ids сохранённых изображений + сопроводительный текст, если вернули."""

    file_ids: list[str]
    text: str | None = None


class _ChatLLM(Protocol):
    async def chat(
        self,
        messages: list[Message],
        *,
        extra_body: JsonObject | None = None,
    ) -> Message: ...


def _image_gen_requirements(*, editing: bool) -> AIRequestRequirements:
    return AIRequestRequirements(
        vision_required=editing,
        image_output_required=True,
    )


def _set_spec_parameters(spec: ImageGenSpec) -> list[str]:
    params: list[str] = []
    if spec.count != 1:
        params.append("count")
    if spec.aspect_ratio is not None:
        params.append("aspect_ratio")
    if spec.image_size is not None:
        params.append("image_size")
    if spec.output_format is not None:
        params.append("output_format")
    if spec.mask_file_id is not None:
        params.append("mask_file_id")
    if spec.seed is not None:
        params.append("seed")
    if spec.negative_prompt is not None:
        params.append("negative_prompt")
    return params


def pick_image_gen_transport(
    resolved: ResolvedAIModel,
    spec: ImageGenSpec,
) -> ImageGenTransport:
    """explicit spec.transport, иначе google → native, остальные → openai_chat."""
    if spec.transport != "auto":
        if spec.transport == "google_native" and resolved.provider != "google":
            raise ValueError(
                "image_gen: google_native transport requires a google model, "
                + f"resolved {resolved.provider}:{resolved.model}"
            )
        return spec.transport
    if resolved.provider == "google":
        return "google_native"
    return "openai_chat"


def validate_image_gen_spec(spec: ImageGenSpec, transport: ImageGenTransport) -> None:
    """Set-параметры vs таблица поддержки транспорта; лимит references native."""
    supported = _TRANSPORT_SUPPORTED_PARAMETERS[transport]
    unsupported = [p for p in _set_spec_parameters(spec) if p not in supported]
    if unsupported:
        raise ValueError(
            f"image_gen: unsupported_parameter:{unsupported[0]} "
            + f"(transport={transport}, unsupported={sorted(unsupported)})"
        )
    if transport == "google_native" and len(spec.references) > _IMAGE_GEN_MAX_REFERENCES:
        raise ValueError(
            f"image_gen: google_native supports at most {_IMAGE_GEN_MAX_REFERENCES} "
            + f"references, got {len(spec.references)}"
        )


class ImageGenClient:
    """Генерация (``generate``) и редактирование (``edit``) изображений.

    Результат — file_ids: native-путь сохраняет байты через FilesService
    (``GENERATED_EPHEMERAL``), chat-путь читает ``file_<hex>`` из ответа модели
    (persist делает LLM-рантайм).
    """

    def __init__(
        self,
        billing_service: BillingService,
        *,
        selection: AISelection | None = None,
    ) -> None:
        self._billing_service: BillingService = billing_service
        self._selection: AISelection | None = selection
        self._llm: dict[tuple[str, str], _ChatLLM] = {}
        self._resolved: dict[AICapability, ResolvedAIModel] = {}

    async def generate(self, spec: ImageGenSpec) -> ImageGenResult:
        if spec.references:
            raise ValueError("image_gen.generate: references require images.edit")
        if spec.mask_file_id is not None:
            raise ValueError("image_gen.generate: mask requires images.edit")
        return await self._run(spec, capability=AICapability.IMAGE_GEN, editing=False)

    async def edit(self, spec: ImageGenSpec) -> ImageGenResult:
        if not spec.references:
            raise ValueError("image_gen.edit: references are required")
        return await self._run(spec, capability=AICapability.IMAGE_EDIT, editing=True)

    def _resolve_model(self, capability: AICapability, *, editing: bool) -> ResolvedAIModel:
        cached = self._resolved.get(capability)
        if cached is not None:
            return cached
        resolved = resolve_ai_model(
            capability,
            requirements=_image_gen_requirements(editing=editing),
            selection=self._selection,
            include_platform_default=True,
        )
        if resolved is None:
            raise ValueError(
                f"ImageGenClient: platform default for capability={capability.value} is not configured"
            )
        self._resolved[capability] = resolved
        return resolved

    async def _run(
        self,
        spec: ImageGenSpec,
        *,
        capability: AICapability,
        editing: bool,
    ) -> ImageGenResult:
        resolved = self._resolve_model(capability, editing=editing)
        transport = pick_image_gen_transport(resolved, spec)
        validate_image_gen_spec(spec, transport)
        logger.info(
            "image_gen.started",
            transport=transport,
            provider=resolved.provider,
            model=resolved.model,
            references=len(spec.references),
            count=spec.count,
        )
        if transport == "google_native":
            return await self._run_google_native(spec, resolved)
        return await self._run_openai_chat(spec, resolved)

    async def _load_reference_bytes(
        self,
        reference_file_ids: tuple[str, ...],
    ) -> list[tuple[bytes, str]]:
        out: list[tuple[bytes, str]] = []
        for file_id in reference_file_ids:
            file_record = await FileRecord.get(file_id)
            if file_record is None:
                raise ValueError(f"ImageGenClient: reference file not found: {file_id}")
            if file_record.company_id is None or file_record.company_id == "":
                raise ValueError(
                    f"ImageGenClient: reference file missing company_id: {file_id}"
                )
            handle = await FileGate().open_record(
                file_record,
                SystemPrincipal(company_id=file_record.company_id),
            )
            file_bytes = await handle.read_bytes()
            if not file_bytes:
                raise ValueError(f"ImageGenClient: reference file empty: {file_id}")
            out.append((file_bytes, file_record.content_type))
        return out

    async def _run_openai_chat(
        self,
        spec: ImageGenSpec,
        resolved: ResolvedAIModel,
    ) -> ImageGenResult:
        parts: list[Part] = []
        if spec.references:
            logger.info("image_gen.references", count=len(spec.references))
            for file_bytes, content_type in await self._load_reference_bytes(spec.references):
                parts.append(Part(raw=file_bytes, media_type=content_type))
        parts.append(Part(text=spec.prompt))

        extra_body: JsonObject = {"modalities": ["image", "text"]}
        image_config: JsonObject = {}
        if spec.aspect_ratio is not None:
            image_config["aspect_ratio"] = spec.aspect_ratio
        if spec.image_size is not None:
            image_config["image_size"] = spec.image_size
        if image_config:
            extra_body["image_config"] = image_config

        llm = self._image_llm(resolved)
        llm_response: Message = await llm.chat(
            [build_a2a_message(role=Role.ROLE_USER, parts=parts)],
            extra_body=extra_body,
        )

        text = get_message_text(llm_response)
        file_ids = [f"file_{m.group(1)}" for m in _FILE_ID_RE.finditer(text)]
        if not file_ids:
            raise RuntimeError("ImageGenClient: LLM response contained no file_id")
        logger.info("image_gen.completed", file_ids=file_ids, count=len(file_ids))
        return ImageGenResult(file_ids=file_ids, text=text or None)

    def _image_llm(self, resolved: ResolvedAIModel) -> _ChatLLM:
        key = (resolved.provider or "", resolved.model or "")
        llm = self._llm.get(key)
        if llm is None:
            llm = create_llm_client_from_ai_model(
                resolved,
                billing_service=self._billing_service,
            )
            self._llm[key] = llm
        return llm

    async def _run_google_native(
        self,
        spec: ImageGenSpec,
        resolved: ResolvedAIModel,
    ) -> ImageGenResult:
        model = (resolved.model or "").strip()
        if model == "":
            raise ValueError("ImageGenClient: google image model is empty")

        references = await self._load_reference_bytes(spec.references)
        api_key = resolve_provider_api_key_for_openai_compatible_calls(
            get_settings().llm,
            "google",
        )
        timeout_s = float(get_settings().nano_banana.timeout)
        url = _GOOGLE_NATIVE_GENERATE_URL.format(model=model)

        file_ids: list[str] = []
        last_text: str | None = None
        for _ in range(spec.count):
            text, image_bytes, content_type = await self._google_native_call(
                url=url,
                api_key=api_key,
                timeout_s=timeout_s,
                spec=spec,
                references=references,
            )
            if image_bytes is None:
                raise RuntimeError(
                    "ImageGenClient: generateContent returned no image "
                    + f"(model={model!r})"
                )
            if text is not None:
                last_text = text
            file_ids.append(
                await self._persist_native_image(
                    image_bytes,
                    content_type=content_type,
                    output_format=spec.output_format,
                    source_file_id=spec.references[0] if spec.references else "",
                    model=model,
                )
            )
        logger.info("image_gen.completed", file_ids=file_ids, count=len(file_ids))
        return ImageGenResult(file_ids=file_ids, text=last_text)

    async def _google_native_call(
        self,
        *,
        url: str,
        api_key: str,
        timeout_s: float,
        spec: ImageGenSpec,
        references: list[tuple[bytes, str]],
    ) -> tuple[str | None, bytes | None, str]:
        parts_payload: list[JsonObject] = [{"text": spec.prompt.strip()}]
        for file_bytes, content_type in references:
            media_type = content_type.strip() or "image/png"
            parts_payload.append(
                {
                    "inline_data": {
                        "mime_type": media_type,
                        "data": base64.b64encode(file_bytes).decode("ascii"),
                    }
                }
            )
        image_config: JsonObject = {}
        if spec.aspect_ratio is not None:
            image_config["aspectRatio"] = spec.aspect_ratio
        if spec.image_size is not None:
            image_config["imageSize"] = spec.image_size
        generation_config: JsonObject = {"responseModalities": ["TEXT", "IMAGE"]}
        if image_config:
            generation_config["imageConfig"] = image_config
        body: JsonObject = {
            "contents": [{"role": "user", "parts": parts_payload}],
            "generationConfig": generation_config,
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
                    "image_gen.google.generateContent",
                )
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"ImageGenClient google generateContent failed: {exc}"
            ) from exc

        response = _GenerateContentResponse.model_validate(payload)
        text: str | None = None
        image_bytes: bytes | None = None
        content_type = "image/png"
        for candidate in response.candidates:
            if candidate.content is None:
                continue
            for part in candidate.content.parts:
                if part.text is not None and part.text.strip():
                    text = part.text
                    continue
                inline = part.inlineData or part.inline_data
                if inline is None or not inline.data.strip():
                    continue
                image_bytes = base64.b64decode(inline.data)
                mime = (inline.mimeType or inline.mime_type or "").strip()
                if mime:
                    content_type = mime
                break
            if image_bytes is not None:
                break
        return text, image_bytes, content_type

    async def _persist_native_image(
        self,
        image_bytes: bytes,
        *,
        content_type: str,
        output_format: str | None,
        source_file_id: str,
        model: str,
    ) -> str:
        out_bytes = image_bytes
        out_content_type = content_type
        if output_format is not None:
            out_bytes, out_content_type = _reencode_image(image_bytes, output_format)
        files_service = FileReader.require_files_service()
        suffix = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/webp": "webp",
        }.get(out_content_type, "png")
        original_name = f"image-gen-edit.{suffix}"
        spec = build_file_create_spec(
            source_kind=FileSourceKind.GENERATED_EPHEMERAL,
            source_ref=FileSourceRef(entity_id=source_file_id or None),
            metadata={
                "image_gen": True,
                "provider": "google",
                "model": model,
            },
        )
        created = await files_service.create(
            spec,
            out_bytes,
            original_name=original_name,
            content_type=out_content_type,
        )
        ref = stored_file_ref(created)
        if ref.file_id is None or not ref.file_id.strip():
            raise ValueError("ImageGenClient: persist returned empty file_id")
        return ref.file_id.strip()


class _GenerateInlineData(BaseModel):
    """``inlineData`` часть generateContent-ответа (wire: extras игнорируются)."""

    data: str = ""
    mimeType: str | None = None
    mime_type: str | None = None


class _GeneratePart(BaseModel):
    text: str | None = None
    inlineData: _GenerateInlineData | None = None
    inline_data: _GenerateInlineData | None = None


class _GenerateCandidateContent(BaseModel):
    parts: list[_GeneratePart] = Field(default_factory=list)


class _GenerateCandidate(BaseModel):
    content: _GenerateCandidateContent | None = None


class _GenerateContentResponse(BaseModel):
    candidates: list[_GenerateCandidate] = Field(default_factory=list)


def _reencode_image(raw: bytes, output_format: str) -> tuple[bytes, str]:
    """Перекодирование в требуемый output_format (native-путь)."""
    pil_format = {"png": "PNG", "jpeg": "JPEG", "webp": "WEBP"}[output_format]
    image = Image.open(BytesIO(raw))
    if output_format == "jpeg":
        image = image.convert("RGB")
    buffer = BytesIO()
    image.save(buffer, format=pil_format, quality=90)
    return buffer.getvalue(), _OUTPUT_FORMAT_CONTENT_TYPE[output_format]
