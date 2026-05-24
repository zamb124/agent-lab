"""Узкие trusted-фасады для встроенных platform tools flows-сервиса."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

from apps.flows.config import FLOWS_PUBLIC_API_PREFIX
from apps.flows.src.clients.mcp_client import get_mcp_client as build_mcp_client
from apps.flows.src.container_state import require_current_container
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.services.flow_speech_resolve import (
    load_flow_speech_layers_from_context_metadata,
    merge_explicit_over_flow_speech_layer,
)
from apps.voice.services.voice_usage import record_stt_usage, record_tts_usage
from core.clients.speech_override import SpeechOverride, SpeechProviderName, SpeechResponseFormat
from core.clients.speech_provider_catalog import STT_TTS_PROVIDER_IDS, VOICE_RESPONSE_FORMAT_IDS
from core.clients.voice_resolver import get_stt_client, get_tts_client
from core.context import get_context
from core.files.audio_probe import probe_audio_duration_seconds_from_upload
from core.files.s3_client import S3ClientFactory
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
    from apps.flows.src.services.lara_facade import LaraFacade
    from apps.flows.src.services.operator_handoff_service import OperatorHandoffService
    from apps.flows.src.services.schedule_service import ScheduleService
    from core.integrations.oauth_service import OAuthService
    from core.state import ExecutionState


def get_operator_handoff_service() -> "OperatorHandoffService":
    return require_current_container().operator_handoff_service


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
) -> Any:
    """Remote code runner для trusted builtins, без передачи FlowContainer в пользовательский код."""
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
    if not isinstance(server_id, str) or server_id.strip() == "":
        raise ValueError("server_id обязателен")
    config = await require_current_container().mcp_server_repository.get(server_id.strip())
    if config is None:
        raise ValueError(f"MCP server not found: {server_id}")
    variables: dict[str, Any] = {}
    if state is not None:
        variables = dict(getattr(state, "variables", {}) or {})
    return await build_mcp_client(
        config=config,
        variables=variables,
        timeout=timeout,
    )


async def call_mcp_tool(
    server_id: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    state: "ExecutionState | None" = None,
    timeout: float = 60.0,
) -> "MCPCallResult":
    """Вызвать MCP tool из trusted platform tool и вернуть `MCPCallResult`."""
    if not isinstance(tool_name, str) or tool_name.strip() == "":
        raise ValueError("tool_name обязателен")
    client = await get_mcp_client(server_id, state=state, timeout=timeout)
    return await client.call_tool(tool_name.strip(), arguments or {})


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

    Провайдер/модель/язык резолвит платформенный `voice_resolver`:
    `override` (этот вызов) → запись `company_voice_providers` для активной
    компании → дефолт `settings.voice.stt`. Никаких прямых импортов
    конкретного клиента в коде агента/тула — всё через фасад.

    Args:
        file_id: идентификатор persisted-аудио в `FileRepository`.
        language: BCP-47 (например `ru-RU`); опционально — переопределяет
            `voice.stt.<provider>.language`.
        provider: явный провайдер для этого вызова (`litserve`, `cloud_ru`,
            `yandex`, `sber`, `mock`); опционально.
        model: явная модель для этого вызова (значение зависит от провайдера);
            опционально.

    Returns:
        Распознанный текст.
    """
    if not isinstance(file_id, str) or file_id.strip() == "":
        raise ValueError("transcribe_audio: file_id обязателен.")

    ctx = get_context()
    if ctx is None or ctx.active_company is None:
        raise ValueError("transcribe_audio: нужен Context с active_company.")
    company_id = ctx.active_company.company_id

    container = require_current_container()
    record = await container.file_processor.get_file_record(file_id.strip())
    if record is None:
        raise ValueError(f"transcribe_audio: файл {file_id!r} не найден.")

    s3 = await container.file_processor.get_s3_client()
    audio_bytes = await s3.download_bytes(record.s3_key, bucket=record.s3_bucket)

    override = SpeechOverride(
        provider=_speech_provider(provider),
        model=model,
        language=language,
    )
    stt_flow, _, _ = load_flow_speech_layers_from_context_metadata(
        ctx.metadata if ctx else None
    )
    override = merge_explicit_over_flow_speech_layer(override, stt_flow)
    stt = await get_stt_client(company_id=company_id, override=override)
    result = await stt.transcribe_audio(
        audio_bytes=audio_bytes,
        file_name=record.original_name,
        mime_type=record.content_type,
        language=override.language,
    )

    if ctx.user is not None:
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
            await record_stt_usage(
                user=ctx.user,
                company=ctx.active_company,
                provider=result.provider,
                audio_seconds=audio_seconds,
                metadata={"endpoint": "flows.transcribe_audio", "file_id": file_id},
            )

    return result.text or ""


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
    или передаёт каналу. Провайдер/модель/голос резолвит `voice_resolver`
    (override → company → deployment-default).

    Args:
        text: текст для озвучивания (обязателен, непустой).
        voice: явный голос для этого вызова (значение зависит от провайдера).
        language: BCP-47 для языка озвучивания.
        provider: явный провайдер (`litserve`, `cloud_ru`, `yandex`, `sber`,
            `mock`).
        model: явная модель (значение зависит от провайдера).
        response_format: контейнер ответа (`wav`, `mp3`, `ogg`, `pcm`, `lpcm`).
        file_name: явное имя сохраняемого файла; по умолчанию формируется как
            `tts_<random>.<ext>` по `response_format`.

    Returns:
        `file_id` сохранённого аудио в `FileRepository`.
    """
    if not isinstance(text, str) or text.strip() == "":
        raise ValueError("synthesize_speech: text обязателен.")

    ctx = get_context()
    if ctx is None or ctx.active_company is None:
        raise ValueError("synthesize_speech: нужен Context с active_company.")
    company_id = ctx.active_company.company_id
    user_id = ctx.user.user_id if ctx.user else None

    override = SpeechOverride(
        provider=_speech_provider(provider),
        model=model,
        voice=voice,
        language=language,
        response_format=_speech_response_format(response_format),
    )
    _, tts_flow, _ = load_flow_speech_layers_from_context_metadata(
        ctx.metadata if ctx else None
    )
    override = merge_explicit_over_flow_speech_layer(override, tts_flow)
    tts = await get_tts_client(company_id=company_id, override=override)
    result = await tts.synthesize(text=text)

    ext = result.response_format if result.response_format else "wav"
    name = file_name if file_name and file_name.strip() else f"tts_{uuid.uuid4().hex[:12]}.{ext}"

    container = require_current_container()
    record = await container.file_processor.persist_uploaded_file(
        data=result.audio_bytes,
        original_name=name,
        content_type=result.mime_type,
        uploaded_by=user_id,
        company_id=company_id,
        public=False,
        download_url_prefix=f"{FLOWS_PUBLIC_API_PREFIX}/files/download",
    )

    if ctx.user is not None:
        await record_tts_usage(
            user=ctx.user,
            company=ctx.active_company,
            provider=result.provider,
            char_count=len(text),
        metadata={"endpoint": "flows.synthesize_speech", "file_id": record.file_id},
        )

    return record.file_id


async def get_google_oauth_token(state: "ExecutionState", service: str) -> str:
    """
    Per-user OAuth для Google API.

    Ищет сохранённый токен в БД. Если нет — бросает FlowInterrupt с ссылкой
    на авторизацию Google. Flow ставится на паузу и автоматически
    продолжается после OAuth callback.

    Args:
        state: ExecutionState текущего flow
        service: идентификатор сервиса (docs, calendar, drive, ...)

    Returns:
        access_token (строка)
    """
    scopes = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive",
    ]

    ctx = get_context()
    if ctx is None or ctx.active_company is None or ctx.user is None:
        raise ValueError("Контекст с активной компанией обязателен для Google OAuth")

    oauth = get_oauth_service()
    credential = await oauth.get_valid_token(
        company_id=ctx.active_company.company_id,
        user_id=ctx.user.user_id,
        provider=IntegrationProvider.GOOGLE,
        service=service,
    )
    if credential:
        logger.debug("Google OAuth: credential found, user=%s, service=%s", ctx.user.user_id, service)
        return credential.access_token

    flow_context: JsonObject = {
        "flow_id": state.session_flow_id,
        "session_id": state.session_id,
        "task_id": state.task_id,
        "context_id": state.context_id,
        "branch_id": state.branch_id,
        "channel": "a2a",
        "user_id": ctx.user.user_id,
        "context_data": ctx.model_dump(mode="json"),
    }
    saved_trace_context = get_current_trace_context()
    if saved_trace_context is not None:
        flow_context["trace_context"] = saved_trace_context

    auth_url = await oauth.build_auth_url(
        provider=IntegrationProvider.GOOGLE,
        service=service,
        scopes=scopes,
        user_id=ctx.user.user_id,
        company_id=ctx.active_company.company_id,
        flow_context=flow_context,
    )
    logger.info("Google OAuth: no credential, raising OAuthInterrupt for user=%s, service=%s", ctx.user.user_id, service)
    raise FlowInterrupt(
        body=OAuthInterrupt(
            question="Для работы с Google необходима авторизация",
            auth_url=auth_url,
            provider="google",
            service=service,
        ),
    )
