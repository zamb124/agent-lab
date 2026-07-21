"""Узкие trusted-фасады для встроенных platform tools сервиса flows."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast

from apps.flows.src.clients.mcp_client import get_mcp_client as build_mcp_client
from apps.flows.src.container_state import require_current_container
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.services.flow_speech_resolve import (
    load_flow_speech_layers_from_context_metadata,
    merge_explicit_over_flow_speech_layer,
)
from apps.voice.services.voice_usage import record_stt_usage, record_tts_usage
from core.ai.runtime import synthesize_speech_audio, transcribe_audio_bytes
from core.clients.google_workspace_auth import (
    GoogleAuthMaterial,
    auth_material_from_execution_variables,
)
from core.clients.google_workspace_scopes import (
    GOOGLE_OAUTH_SERVICE_CANONICAL,
    GOOGLE_OAUTH_SERVICE_PRIOR_KEYS,
    scopes_for_google_service,
)
from core.clients.speech_override import SpeechOverride, SpeechProviderName, SpeechResponseFormat
from core.clients.speech_provider_catalog import STT_TTS_PROVIDER_IDS, VOICE_RESPONSE_FORMAT_IDS
from core.context import get_context
from core.files.audio_probe import probe_audio_duration_seconds_from_upload
from core.files.create_spec import FileCreateSpec, FilePostCreate, FileSourceKind, FileSourceRef
from core.files.registry import default_retention_for_source
from core.files.s3_client import S3ClientFactory
from core.integrations.constants import TOKEN_TYPE_SERVICE_ACCOUNT
from core.integrations.models import IntegrationProvider
from core.logging import get_logger
from core.state.interrupt import OAuthInterrupt
from core.text_transforms import TextTransformService
from core.tracing.context import get_current_trace_context
from core.types import JsonObject

logger = get_logger(__name__)

if TYPE_CHECKING:
    from apps.flows.src.clients.mcp_client import MCPClient
    from apps.flows.src.models.mcp import MCPCallResult
    from apps.flows.src.runners.remote import RemoteCodeRunner
    from apps.flows.src.services.agent_skill_service import AgentSkillService
    from apps.flows.src.services.hitl_work_item_service import HitlWorkItemService
    from apps.flows.src.services.lara_facade import LaraFacade
    from apps.flows.src.services.schedule_service import ScheduleService
    from core.integrations.oauth_service import OAuthService
    from core.state import ExecutionState
    from core.worktracker.service import WorkItemService


def get_work_item_service() -> "WorkItemService":
    return require_current_container().work_item_service


def get_agent_skill_service() -> "AgentSkillService":
    return require_current_container().agent_skill_service


def get_hitl_work_item_service() -> "HitlWorkItemService":
    return require_current_container().hitl_work_item_service


def get_schedule_service() -> "ScheduleService":
    return require_current_container().schedule_service


def get_oauth_service() -> "OAuthService":
    return require_current_container().oauth_service


def get_lara_facade() -> "LaraFacade":
    return require_current_container().lara_facade


_SPEECH_PROVIDERS = STT_TTS_PROVIDER_IDS
_SPEECH_RESPONSE_FORMATS = VOICE_RESPONSE_FORMAT_IDS


def _speech_provider(value: str | None) -> SpeechProviderName | None:
    if value is None:
        return None
    if value not in _SPEECH_PROVIDERS:
        raise ValueError(f"Unknown speech provider: {value}")
    return cast(SpeechProviderName, value)


def _speech_response_format(value: str | None) -> SpeechResponseFormat | None:
    if value is None:
        return None
    if value not in _SPEECH_RESPONSE_FORMATS:
        raise ValueError(f"Unknown speech response format: {value}")
    return cast(SpeechResponseFormat, value)


def get_code_runner(
    language: str = "python",
) -> "RemoteCodeRunner":
    """Удалённый code runner для trusted builtins, без передачи FlowContainer в пользовательский код."""
    return require_current_container().get_code_runner(language=language)


_text_transform_service: "TextTransformService | None" = None


def get_text_transform_service() -> "TextTransformService":
    """Суммаризация и Markdown для trusted builtins."""
    global _text_transform_service
    if _text_transform_service is None:
        _text_transform_service = TextTransformService()
    return _text_transform_service


async def get_mcp_client(
    server_id: str,
    *,
    state: "ExecutionState | None" = None,
    timeout: float = 60.0,
) -> "MCPClient":
    """Вернуть MCP-клиент по `server_id` для trusted platform tool."""
    if server_id.strip() == "":
        raise ValueError("server_id обязателен")
    config = await require_current_container().mcp_server_repository.get(server_id.strip())
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
    """Вызвать MCP tool из trusted platform tool и вернуть `MCPCallResult`."""
    if tool_name.strip() == "":
        raise ValueError("tool_name обязателен")
    client = await get_mcp_client(server_id, state=state, timeout=timeout)
    return await client.call_tool(tool_name.strip(), arguments if arguments is not None else {})


async def get_file_bytes(file_id: str) -> bytes:
    """Скачивает содержимое файла по ID из хранилища платформы (FileRepository + S3)."""
    container = require_current_container()
    record = await container.file_repository.get(file_id)
    if record is None:
        raise ValueError(f"Файл {file_id} не найден в хранилище")
    s3 = S3ClientFactory.create_client_for_bucket(record.s3_bucket)
    return await s3.download_bytes(record.s3_key)


async def transcribe_audio(
    file_id: str,
    *,
    language: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> str:
    """
    STT: распознаёт persisted-аудио по `file_id` и возвращает текст.

    Провайдер/модель/язык резолвит платформенный `core.ai.runtime`:
    `override` (этот вызов) → запись `company_voice_providers` для активной
    компании → дефолт `settings.voice.stt`. Никаких прямых импортов
    конкретного клиента в коде агента/тула — всё через фасад.

    Аргументы:
        file_id: идентификатор persisted-аудио в `FileRepository`.
        language: BCP-47 (например `ru-RU`); опционально — переопределяет
            `voice.stt.<provider>.language`.
        provider: явный провайдер для этого вызова (`litserve`, `cloud_ru`,
            `yandex`, `sber`, `mock`); опционально.
        model: явная модель для этого вызова (значение зависит от провайдера);
            опционально.

    Возвращает:
        Распознанный текст.
    """
    if file_id.strip() == "":
        raise ValueError("transcribe_audio: file_id обязателен.")

    ctx = get_context()
    if ctx is None or ctx.active_company is None:
        raise ValueError("transcribe_audio: нужен Context с active_company.")
    company_id = ctx.active_company.company_id

    container = require_current_container()
    record = await container.files_service.get(file_id.strip())
    s3 = S3ClientFactory.create_client_for_bucket(record.s3_bucket)
    audio_bytes = await s3.download_bytes(record.s3_key, bucket=record.s3_bucket)

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
        _ = await record_stt_usage(
            user=ctx.user,
            company=ctx.active_company,
            provider=result.provider,
            audio_seconds=audio_seconds,
            metadata={"endpoint": "flows.transcribe_audio", "file_id": file_id},
        )

    return result.text


async def synthesize_speech(
    text: str,
    *,
    voice: str | None = None,
    language: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    response_format: str | None = None,
    file_name: str | None = None,
) -> str:
    """
    TTS: синтезирует речь и сохраняет результат в `FileRepository` + S3.

    Возвращает `file_id` сохранённого аудио — этот id агент кладёт в ответ
    или передаёт каналу. Провайдер/модель/голос резолвит `core.ai.runtime`
    (override → company → deployment-default).

    Аргументы:
        text: текст для озвучивания (обязателен, непустой).
        voice: явный голос для этого вызова (значение зависит от провайдера).
        language: BCP-47 для языка озвучивания.
        provider: явный провайдер (`litserve`, `cloud_ru`, `yandex`, `sber`,
            `mock`).
        model: явная модель (значение зависит от провайдера).
        response_format: контейнер ответа (`wav`, `mp3`, `ogg`, `pcm`, `lpcm`).
        file_name: явное имя сохраняемого файла; по умолчанию формируется как
            `tts_<random>.<ext>` по `response_format`.

    Возвращает:
        `file_id` сохранённого аудио в `FileRepository`.
    """
    if text.strip() == "":
        raise ValueError("synthesize_speech: text обязателен.")

    ctx = get_context()
    if ctx is None or ctx.active_company is None:
        raise ValueError("synthesize_speech: нужен Context с active_company.")
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

    container = require_current_container()
    spec = FileCreateSpec(
        source_kind=FileSourceKind.GENERATED_EPHEMERAL,
        source_ref=FileSourceRef(),
        retention=default_retention_for_source(FileSourceKind.GENERATED_EPHEMERAL),
        post_create=FilePostCreate(is_public=False),
    )
    record = await container.files_service.create(
        spec=spec,
        data=result.audio_bytes,
        original_name=name,
        content_type=result.mime_type,
    )

    _ = await record_tts_usage(
        user=ctx.user,
        company=ctx.active_company,
        provider=result.provider,
        char_count=len(text),
        metadata={"endpoint": "flows.synthesize_speech", "file_id": record.file_id},
    )

    return record.file_id


async def resolve_google_workspace_auth(state: "ExecutionState") -> GoogleAuthMaterial:
    """
    Auth для Google Docs/Sheets tools.

    Порядок: state.variables → user service=workspace → prior docs/sheets credentials →
    company user_id=__company__ SA → OAuthInterrupt (Connect Google, service=workspace).
    """
    from_vars = auth_material_from_execution_variables(state.variables)
    if from_vars is not None:
        return from_vars

    ctx = get_context()
    if ctx is None or ctx.active_company is None:
        raise ValueError("Контекст с активной компанией обязателен для Google Workspace auth")

    company_id = ctx.active_company.company_id
    user_id = ctx.user.user_id
    oauth = get_oauth_service()

    workspace_cred = await oauth.get_valid_token(
        company_id=company_id,
        user_id=user_id,
        provider=IntegrationProvider.GOOGLE,
        service=GOOGLE_OAUTH_SERVICE_CANONICAL,
    )
    if workspace_cred is not None and workspace_cred.token_type != TOKEN_TYPE_SERVICE_ACCOUNT:
        logger.debug(
            "Google Workspace: user workspace credential, user=%s",
            user_id,
        )
        return GoogleAuthMaterial(access_token=workspace_cred.access_token)

    for prior_service in GOOGLE_OAUTH_SERVICE_PRIOR_KEYS:
        prior_cred = await oauth.get_valid_token(
            company_id=company_id,
            user_id=user_id,
            provider=IntegrationProvider.GOOGLE,
            service=prior_service,
        )
        if prior_cred is not None and prior_cred.token_type != TOKEN_TYPE_SERVICE_ACCOUNT:
            logger.debug(
                "Google Workspace: prior credential service=%s user=%s",
                prior_service,
                user_id,
            )
            return GoogleAuthMaterial(access_token=prior_cred.access_token)

    company_material = await (
        require_current_container()
        .company_integration_credential_service
        .get_google_workspace_auth_material(company_id)
    )
    if company_material is not None:
        logger.debug("Google Workspace: company SA credential, company=%s", company_id)
        return company_material

    scopes = scopes_for_google_service(GOOGLE_OAUTH_SERVICE_CANONICAL)
    flow_context: JsonObject = {
        "flow_id": state.session_flow_id,
        "session_id": state.session_id,
        "task_id": state.task_id,
        "context_id": state.context_id,
        "branch_id": state.branch_id,
        "channel": "a2a",
        "user_id": user_id,
        "context_data": ctx.model_dump(mode="json"),
    }
    saved_trace_context = get_current_trace_context()
    if saved_trace_context is not None:
        flow_context["trace_context"] = saved_trace_context

    auth_url = await oauth.build_auth_url(
        provider=IntegrationProvider.GOOGLE,
        service=GOOGLE_OAUTH_SERVICE_CANONICAL,
        scopes=scopes,
        user_id=user_id,
        company_id=company_id,
        flow_context=flow_context,
    )
    logger.info(
        "Google Workspace: no credential, raising OAuthInterrupt for user=%s",
        user_id,
    )
    raise FlowInterrupt(
        body=OAuthInterrupt(
            # UI переводит через platform_chat.interrupt_oauth_workspace_*;
            # строка — стабильный ключ для non-SPA клиентов.
            question="oauth_required.google.workspace",
            auth_url=auth_url,
            provider="google",
            service=GOOGLE_OAUTH_SERVICE_CANONICAL,
        ),
    )


async def get_google_oauth_token(state: "ExecutionState", service: str) -> str:
    """
    Thin helper: resolve auth and return access_token only.

    New tools must use resolve_google_workspace_auth (supports company SA).
    service is ignored for lookup order; interrupt always uses workspace.
    """
    _ = service
    material = await resolve_google_workspace_auth(state)
    if material.access_token is None or material.access_token.strip() == "":
        raise ValueError(
            "get_google_oauth_token requires OAuth access_token; "
            + "company SA needs resolve_google_workspace_auth"
        )
    return material.access_token
