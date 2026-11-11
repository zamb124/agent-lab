"""
Тулы универсального image gen API в flow.

images_generate — capability images.generate (prompt → file_ids);
images_edit — capability images.edit (prompt + references → file_ids).
"""

from typing import Literal

from pydantic import BaseModel, Field

from apps.flows.config import get_settings as get_flows_settings
from apps.flows.src.files.state_file_refs import upsert_state_file
from apps.flows.src.runners.capability_context import capability_execution_context
from apps.flows.src.services.flow_ui_cards import show_files
from apps.flows.src.state import ExecutionState
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.capabilities import CapabilityCallRequest
from core.clients.capability_gateway_client import CapabilityGatewayClient
from core.clients.image_gen import ImageGenReference
from core.files.file_ref import FileRef
from core.models.base import StrictBaseModel
from core.types import JsonObject, require_json_object


class _ImageGenBaseArgs(StrictBaseModel):
    prompt: str = Field(
        ...,
        min_length=1,
        description="Текстовый промпт / инструкция редактирования.",
    )
    count: int = Field(
        default=1,
        ge=1,
        le=4,
        description="Число изображений 1..4.",
    )
    aspect_ratio: str | None = Field(
        default=None,
        description="Соотношение сторон 'W:H' (например '1:1', '3:2', '16:9'); null — по умолчанию модели.",
    )
    image_size: Literal["1K", "2K", "4K"] | None = Field(
        default=None,
        description="Размер выхода; null — по умолчанию модели.",
    )
    output_format: Literal["png", "jpeg", "webp"] | None = Field(
        default=None,
        description="Формат выходного файла; null — формат провайдера.",
    )
    include_bytes_b64: bool = Field(
        default=False,
        description="True — в files[] добавить bytes_b64 для превью в JSON tree.",
    )


class ImagesGenerateArgs(_ImageGenBaseArgs):
    seed: int | None = Field(
        default=None,
        description="Seed генерации; unsupported_parameter, если модель не умеет.",
    )
    negative_prompt: str | None = Field(
        default=None,
        description="Негативный промпт; unsupported_parameter, если модель не умеет.",
    )


class ImagesEditArgs(_ImageGenBaseArgs):
    references: list[ImageGenReference] = Field(
        ...,
        min_length=1,
        description=(
            "Референс-изображения: [{file_id}] или [{file_id, page}] — "
            "page (0-based) растризует страницу PDF в картинку до редактирования."
        ),
    )
    mask_file_id: str | None = Field(
        default=None,
        description="file_id маски; unsupported_parameter, если модель не умеет mask.",
    )
    seed: int | None = Field(
        default=None,
        description="Seed генерации; unsupported_parameter, если модель не умеет.",
    )
    negative_prompt: str | None = Field(
        default=None,
        description="Негативный промпт; unsupported_parameter, если модель не умеет.",
    )


def _image_gen_kwargs(args: BaseModel) -> JsonObject:
    return require_json_object(
        args.model_dump(mode="json", exclude_none=True),
        "images.args",
    )


def _apply_image_result(state: ExecutionState, response: JsonObject) -> JsonObject:
    files = response.get("files")
    file_refs: list[FileRef] = []
    if isinstance(files, list):
        for item in files:
            payload = (
                {k: v for k, v in item.items() if k != "bytes_b64"}
                if isinstance(item, dict)
                else item
            )
            file_refs.append(FileRef.model_validate(payload))
    for file_ref in file_refs:
        upsert_state_file(state, file_ref)
    if file_refs:
        _ = show_files(state, file_refs)
    return response


@tool(
    name="images_generate",
    description=(
        "Generate images from a text prompt via universal image API "
        "(AICapability.IMAGE_GEN). Returns files[]={file_id, url, content_type, "
        "original_name} (+bytes_b64 when include_bytes_b64); produced files are "
        "also added to state.files. Optional hints: count, aspect_ratio 'W:H', "
        "image_size 1K/2K/4K, output_format, seed, negative_prompt — "
        "unsupported hints fail with unsupported_parameter."
    ),
    tags=["images"],
    parameters_model=ImagesGenerateArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
    effects=["create"],
)
async def images_generate(
    *,
    state: ExecutionState,
    prompt: str,
    count: int = 1,
    aspect_ratio: str | None = None,
    image_size: Literal["1K", "2K", "4K"] | None = None,
    output_format: Literal["png", "jpeg", "webp"] | None = None,
    seed: int | None = None,
    negative_prompt: str | None = None,
    include_bytes_b64: bool = False,
) -> JsonObject:
    args = ImagesGenerateArgs(
        prompt=prompt,
        count=count,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
        output_format=output_format,
        seed=seed,
        negative_prompt=negative_prompt,
        include_bytes_b64=include_bytes_b64,
    )
    timeout = float(get_flows_settings().node_execution_wall_time_cap_seconds)
    execution_context = capability_execution_context(
        state,
        allowed_capabilities=["images.generate"],
    )
    response = await CapabilityGatewayClient().call(
        CapabilityCallRequest(
            context=execution_context,
            name="images.generate",
            kwargs=_image_gen_kwargs(args),
        ),
        timeout=timeout,
    )
    result = require_json_object(response.result, "images_generate.result")
    return _apply_image_result(state, result)


@tool(
    name="images_edit",
    description=(
        "Edit or generate images from a prompt plus reference images via "
        "universal image API (AICapability.IMAGE_GEN). references[] items are "
        "{file_id} or {file_id, page} — a PDF page is rasterized to an image "
        "first. Cropping and instruction edits are prompt-driven; there is no "
        "bbox. Returns files[]={file_id, url, content_type, original_name} "
        "(+bytes_b64); produced files are also added to state.files."
    ),
    tags=["images"],
    parameters_model=ImagesEditArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
    effects=["create"],
)
async def images_edit(
    *,
    state: ExecutionState,
    prompt: str,
    references: list[ImageGenReference],
    mask_file_id: str | None = None,
    count: int = 1,
    aspect_ratio: str | None = None,
    image_size: Literal["1K", "2K", "4K"] | None = None,
    output_format: Literal["png", "jpeg", "webp"] | None = None,
    seed: int | None = None,
    negative_prompt: str | None = None,
    include_bytes_b64: bool = False,
) -> JsonObject:
    args = ImagesEditArgs(
        prompt=prompt,
        references=references,
        mask_file_id=mask_file_id,
        count=count,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
        output_format=output_format,
        seed=seed,
        negative_prompt=negative_prompt,
        include_bytes_b64=include_bytes_b64,
    )
    timeout = float(get_flows_settings().node_execution_wall_time_cap_seconds)
    execution_context = capability_execution_context(
        state,
        allowed_capabilities=["images.edit"],
    )
    response = await CapabilityGatewayClient().call(
        CapabilityCallRequest(
            context=execution_context,
            name="images.edit",
            kwargs=_image_gen_kwargs(args),
        ),
        timeout=timeout,
    )
    result = require_json_object(response.result, "images_edit.result")
    return _apply_image_result(state, result)
