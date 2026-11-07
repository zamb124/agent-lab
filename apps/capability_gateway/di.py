"""DI процесса capability_gateway: trusted gateway sandbox capabilities."""

from collections.abc import AsyncIterator
from typing import Annotated

from apps.capability_gateway.services.registry import CapabilityRegistry
from core.di import ServiceDi, http_di, recipe, task_di
from core.di.platform import (
    authz_service,
    billing_service,
    files_service,
    redis_client,
    shared_storage,
)
from core.files.reader import FileReader
from core.files.service import FilesService
from core.text_transforms import TextTransformService


@recipe
async def configure_file_reader_asset_persist(
    files_service: FilesService,
) -> AsyncIterator[None]:
    """Nested persist (refs) для files.read page_summarizations / nested_mode."""
    FileReader.configure_asset_persist(files_service)
    yield


@recipe
async def configure_file_reader_text_transform(
    text_transform: TextTransformService,
) -> AsyncIterator[None]:
    """LLM-суммаризация страниц FileReader через TextTransformService процесса."""
    FileReader.configure_text_transform(text_transform)
    yield


CAPABILITY_GATEWAY_LIFECYCLE = (
    configure_file_reader_asset_persist,
    configure_file_reader_text_transform,
)


class CapabilityGatewayDi(
    ServiceDi,
    recipes=(
        redis_client,
        authz_service,
        files_service,
        shared_storage,
        billing_service,
    ),
):
    capability_registry: CapabilityRegistry


Di = Annotated[CapabilityGatewayDi, http_di(CapabilityGatewayDi), task_di(CapabilityGatewayDi)]
