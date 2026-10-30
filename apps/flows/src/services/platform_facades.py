"""Helpers for flows process: speech, MCP, Google auth re-export.

Builtin tools use XxxClient — not this module.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from apps.flows.src.models.mcp import MCPServerConfig
from apps.flows.src.services.flow_speech_resolve import (
    load_flow_speech_layers_from_context_metadata,
    merge_explicit_over_flow_speech_layer,
)
from apps.flows.src.services.google_workspace_client import GoogleWorkspaceClient
from apps.flows.src.services.mcp_client import get_mcp_client as build_mcp_client
from core.ai.runtime import synthesize_speech_audio, transcribe_audio_bytes
from core.billing.service import COST_ORIGIN_PLATFORM
from core.billing.speech_usage import record_stt_usage_span, record_tts_usage_span
from core.clients.files_client import FilesClient
from core.clients.google_workspace_auth import GoogleAuthMaterial
from core.clients.speech_override import SpeechOverride, SpeechProviderName, SpeechResponseFormat
from core.clients.speech_provider_catalog import STT_TTS_PROVIDER_IDS, VOICE_RESPONSE_FORMAT_IDS
from core.context import get_context
from core.files.audio_probe import probe_audio_duration_seconds_from_upload
from core.files.create_spec import FileCreateSpec, FilePostCreate, FileSourceKind, FileSourceRef
from core.files.object_store.gate import FileGate
from core.files.object_store.principals import SystemPrincipal
from core.files.registry import default_retention_for_source
from core.files.service import FilesService
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)

if TYPE_CHECKING:
    from apps.flows.src.models.mcp import MCPCallResult
    from apps.flows.src.services.mcp_client import MCPClient
    from apps.flows.src.state import ExecutionState

_SPEECH_PROVIDERS = STT_TTS_PROVIDER_IDS
_SPEECH_RESPONSE_FORMATS = VOICE_RESPONSE_FORMAT_IDS


def _speech_provider(value: str | None) -> SpeechProviderName | None:
    if value is None:
        return None
    for provider in _SPEECH_PROVIDERS:
        if provider == value:
            return provider
    raise ValueError(f"Unknown speech provider: {value}")


def _speech_response_format(value: str | None) -> SpeechResponseFormat | None:
    if value is None:
        return None
    for response_format in _SPEECH_RESPONSE_FORMATS:
        if response_format == value:
            return response_format
    raise ValueError(f"Unknown speech response format: {value}")


async def get_mcp_client(
    server_id: str,
    *,
    state: "ExecutionState | None" = None,
    timeout: float = 60.0,
) -> "MCPClient":
    """Вернуть MCP-клиент по `server_id` для trusted platform code."""
    if server_id.strip() == "":
        raise ValueError("server_id is required")
    config = await MCPServerConfig.get(MCPServerConfig.server_row_id_for_active_company(server_id.strip()))
    if config is None:
        raise ValueError(f"MCP server not found: {server_id}")
    variables: JsonObject = state.variables if state is not None else {}
    return await build_mcp_client(
        config=config,
        variables=variables,
        timeout=timeout,
    )


async def call_mcp_tool(
    server_id: str,
    tool_name: str,
    arguments: JsonObject | None = None,
    *,
    state: "ExecutionState | None" = None,
    timeout: float = 60.0,
) -> "MCPCallResult":
    """Вызвать MCP tool и вернуть `MCPCallResult`."""
    if tool_name.strip() == "":
        raise ValueError("tool_name is required")
    client = await get_mcp_client(server_id, state=state, timeout=timeout)
    return await client.call_tool(tool_name.strip(), arguments if arguments is not None else {})


async def get_file_bytes(file_id: str) -> bytes:
    """Скачивает содержимое файла по ID (FileRepository + S3)."""
    return await FilesClient().get_bytes(file_id)


async def transcribe_audio(
    file_id: str,
    *,
    files_service: FilesService,
    language: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> str:
    """STT: распознаёт persisted-аудио по `file_id` и возвращает текст."""
    if file_id.strip() == "":
        raise ValueError("transcribe_audio: file_id is required.")

    ctx = get_context()
    if ctx is None or ctx.active_company is None:
        raise ValueError("transcribe_audio: Context with active_company is required.")
    company_id = ctx.active_company.company_id

    record = await files_service.get(file_id.strip())
    if record.company_id is None or record.company_id == "":
        raise ValueError(f"file {file_id!r} has no company_id")
    handle = await FileGate().open_record(
        record,
        SystemPrincipal(company_id=record.company_id),
    )
    audio_bytes = await handle.read_bytes()

    override = SpeechOverride(
        provider=_speech_provider(provider),
        model=model,
        language=language,
    )
    stt_flow, _, _ = load_flow_speech_layers_from_context_metadata(ctx.metadata)
    override = merge_explicit_over_flow_speech_layer(override, stt_flow)
    result = await transcribe_audio_bytes(
        company_id=company_id,
        audio_bytes=audio_bytes,
        file_name=record.original_name,
        content_type=record.content_type,
        override=override,
        language=override.language,
    )

    try:
        audio_seconds = await probe_audio_duration_seconds_from_upload(
            data=audio_bytes, file_name=record.original_name
        )
    except ValueError as exc:
        logger.warning(
            "flows.transcribe_audio.stt_usage_skipped",
            reason=str(exc),
            company_id=company_id,
            user_id=ctx.user.user_id,
            provider=result.provider,
            file_id=file_id.strip(),
        )
    else:
        await record_stt_usage_span(
            user=ctx.user,
            company=ctx.active_company,
            provider=result.provider,
            audio_seconds=audio_seconds,
            cost_origin=COST_ORIGIN_PLATFORM,
            extra_attributes={"endpoint": "flows.transcribe_audio", "file_id": file_id},
        )

    return result.text


async def synthesize_speech(
    text: str,
    *,
    files_service: FilesService,
    voice: str | None = None,
    language: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    response_format: str | None = None,
    file_name: str | None = None,
) -> str:
    """TTS: синтезирует речь и сохраняет результат; возвращает `file_id`."""
    if text.strip() == "":
        raise ValueError("synthesize_speech: text is required.")

    ctx = get_context()
    if ctx is None or ctx.active_company is None:
        raise ValueError("synthesize_speech: Context with active_company is required.")
    company_id = ctx.active_company.company_id

    override = SpeechOverride(
        provider=_speech_provider(provider),
        model=model,
        voice=voice,
        language=language,
        response_format=_speech_response_format(response_format),
    )
    _, tts_flow, _ = load_flow_speech_layers_from_context_metadata(ctx.metadata)
    override = merge_explicit_over_flow_speech_layer(override, tts_flow)
    result = await synthesize_speech_audio(
        company_id=company_id,
        text=text,
        override=override,
    )

    ext = result.response_format if result.response_format else "wav"
    name = file_name if file_name and file_name.strip() else f"tts_{uuid.uuid4().hex[:12]}.{ext}"

    spec = FileCreateSpec(
        source_kind=FileSourceKind.GENERATED_EPHEMERAL,
        source_ref=FileSourceRef(),
        retention=default_retention_for_source(FileSourceKind.GENERATED_EPHEMERAL),
        post_create=FilePostCreate(is_public=False),
    )
    record = await files_service.create(
        spec=spec,
        data=result.audio_bytes,
        original_name=name,
        content_type=result.mime_type,
    )

    await record_tts_usage_span(
        user=ctx.user,
        company=ctx.active_company,
        provider=result.provider,
        char_count=len(text),
        cost_origin=COST_ORIGIN_PLATFORM,
        extra_attributes={"endpoint": "flows.synthesize_speech", "file_id": record.file_id},
    )

    return record.file_id


async def get_google_oauth_token(
    state: "ExecutionState",
    service: str,
    google_workspace_client: GoogleWorkspaceClient,
) -> str:
    """Thin helper: resolve auth and return access_token only."""
    _ = service
    material = await google_workspace_client.resolve_auth(state)
    if material.access_token is None or material.access_token.strip() == "":
        raise ValueError(
            "get_google_oauth_token requires OAuth access_token; "
            + "company SA needs GoogleWorkspaceClient().resolve_auth"
        )
    return material.access_token


__all__ = [
    "GoogleAuthMaterial",
    "call_mcp_tool",
    "get_file_bytes",
    "get_google_oauth_token",
    "get_mcp_client",
    "synthesize_speech",
    "transcribe_audio",
]
