"""
API per-company override провайдеров речи (`company_voice_providers`).

Контракт REST-зеркала команд: список и upsert/delete для kind-ов
(`stt`, `tts`). VAD настраивается только на уровне развёртывания.
Менять может только участник целевой компании c
ролью `owner`/`admin`. Чтение — любой участник этой же компании.

PUT: если поле `secrets` отсутствует в теле JSON — сохранённые ключи в JSONB
не изменяются; если `secrets: null` — колонка `secrets` очищается; если объект —
выполняется merge (в `merge_secrets`, см. `core/db/company_voice_provider_secrets.py`):
для ключа из patch значение `null` или `""` удаляет этот ключ; непустая строка задаёт значение.

После любых изменений сбрасывается in-memory TTL-кэш `voice_resolver`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from apps.voice.api.voice_providers_catalog_helpers import (
    CompanySecretsMetaDTO,
    allowed_secret_keys,
    secrets_dict_to_meta,
)
from apps.voice.di import Di
from core.ai.runtime import invalidate_voice_company_overrides_cache
from core.authz.models import AuthzObject
from core.clients.speech_provider_catalog import (
    STT_TTS_PROVIDER_IDS,
    cloud_ru_stt_model_ids,
    cloud_ru_tts_model_ids,
)
from core.context import require_context
from core.logging import get_logger
from core.models.company_voice_provider_secrets import (
    SecretsPatchValue,
    merge_secrets,
    unset_secrets_sentinel,
)
from core.models.provider_litserve_model import litserve_catalog_entries
from core.models.voice_models import CompanyVoiceProvider, VoiceKind
from core.platform_brand.resolver import resolve_brand_or_primary
from core.websocket import WsCommandError, raise_invalid

if TYPE_CHECKING:
    from core.models.identity_models import User

logger = get_logger(__name__)
router = APIRouter(
    prefix="/api/v1/companies/{company_id}/voice-providers",
    tags=["frontend", "voice"],
)

_VOICE_KINDS: tuple[VoiceKind, ...] = ("stt", "tts")

_YANDEX_SPEECH_MODELS = ("general",)
_SBER_SPEECH_MODELS = ("general",)


class CompanyVoiceProviderItem(BaseModel):
    """Одна запись `company_voice_providers` (ответ GET/PUT без сырых секретов)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    kind: Literal["stt", "tts"] = Field(description="Тип провайдера речи.")
    provider: str = Field(description="Имя провайдера.")
    model: str | None = Field(default=None)
    voice: str | None = Field(default=None)
    language: str | None = Field(default=None)
    sample_rate: int | None = Field(default=None, gt=0)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    response_format: Literal["wav", "mp3", "ogg", "pcm", "lpcm"] | None = Field(
        default=None
    )
    secrets_meta: CompanySecretsMetaDTO | None = Field(default=None)


class CompanyVoiceProvidersResponse(BaseModel):
    """Список настроек речи компании (stt/tts)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    company_id: str = Field(description="ID компании.")
    items: list[CompanyVoiceProviderItem] = Field(default_factory=list)


class CompanyVoiceProviderUpsertRequest(BaseModel):
    """Тело PUT-запроса для одного kind-а."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, description="Имя провайдера речи.")
    model: str | None = Field(default=None)
    voice: str | None = Field(default=None)
    language: str | None = Field(default=None)
    sample_rate: int | None = Field(default=None, gt=0)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    response_format: Literal["wav", "mp3", "ogg", "pcm", "lpcm"] | None = Field(
        default=None
    )
    secrets: dict[str, str | None] | None = Field(
        default=None,
        description=(
            "Merge-patch для колонки `secrets`; если поля нет в JSON — сохранённые "
            "ключи не меняются; если `secrets: null` — колонка очищается; в объект patch "
            "`null`/`\"\"` по ключу удаляет ключ, непустая строка — задаёт значение."
        ),
    )

async def _ensure_user_can_read_company(
    di: Di, user: "User", company_id: str
) -> None:
    await di.authz_service.require_can_view(
        AuthzObject.company(company_id),
        user_id=user.user_id,
    )


async def _ensure_user_can_manage_company(
    di: Di, user: "User", company_id: str
) -> None:
    await di.authz_service.require_company_admin(
        company_id=company_id,
        user_id=user.user_id,
    )


def _reject_vad_path_kind(kind: str) -> None:
    if kind == "vad":
        raise WsCommandError(
            "gone",
            "VAD is configured at deployment level; per-company override was removed.",
            error_code="gone",
        )


def _validate_kind(kind: str) -> VoiceKind:
    if kind == "stt":
        return "stt"
    if kind == "tts":
        return "tts"
    raise WsCommandError(
        "ws_invalid_payload",
        f"Unknown kind: {kind!r}. Allowed: {', '.join(_VOICE_KINDS)}",
        error_code="ws_invalid_payload",
    )


def _validate_provider(kind: VoiceKind, provider: str) -> None:
    allowed = STT_TTS_PROVIDER_IDS
    if provider not in allowed:
        raise WsCommandError(
            "ws_invalid_payload",
            f"Unknown provider {provider!r} for kind={kind!r}; allowed: {', '.join(sorted(allowed))}",
            error_code="ws_invalid_payload",
        )


async def _validate_model_for_voice(
    *,
    kind: VoiceKind,
    provider: str,
    model_value: str | None,
    voice_product_name: str,
) -> None:
    """Если model задан — должен быть из каталога провайдера; пустое значение допустимо
    для всех провайдеров (резолвер `voice_resolver` подставит default из настроек)."""
    if provider != "litserve":
        if provider == "cloud_ru":
            if model_value is None or model_value == "":
                return
            allowed = cloud_ru_stt_model_ids() if kind == "stt" else cloud_ru_tts_model_ids()
            if model_value not in allowed:
                raise WsCommandError(
                    "ws_invalid_payload",
                    f"model must be one of: {', '.join(allowed)}",
                    error_code="ws_invalid_payload",
                )
            return
        if provider == "yandex":
            if model_value is None or model_value == "":
                return
            if model_value not in _YANDEX_SPEECH_MODELS:
                raise WsCommandError(
                    "ws_invalid_payload",
                    f"Yandex model must be one of: {', '.join(_YANDEX_SPEECH_MODELS)}",
                    error_code="ws_invalid_payload",
                )
            return
        if provider == "sber":
            if model_value is None or model_value == "":
                return
            if model_value not in _SBER_SPEECH_MODELS:
                raise WsCommandError(
                    "ws_invalid_payload",
                    f"Sber model must be one of: {', '.join(_SBER_SPEECH_MODELS)}",
                    error_code="ws_invalid_payload",
                )
            return
        return

    if model_value is None or model_value == "":
        return

    entries = await litserve_catalog_entries()
    if kind == "stt":
        allowed = frozenset(m.api_model_id for m in entries.stt)
    else:
        allowed = frozenset(m.api_model_id for m in entries.tts)

    if model_value not in allowed:
        raise WsCommandError(
            "ws_invalid_payload",
            f"Unknown model {voice_product_name}: {model_value!r}",
            error_code="ws_invalid_payload",
        )


def _item_kind(value: str) -> Literal["stt", "tts"]:
    if value == "stt":
        return "stt"
    if value == "tts":
        return "tts"
    raise WsCommandError("internal", f"Invalid kind in DB: {value!r}", error_code="internal")


def _response_format(
    value: str | None,
) -> Literal["wav", "mp3", "ogg", "pcm", "lpcm"] | None:
    if value is None:
        return None
    if value == "wav":
        return "wav"
    if value == "mp3":
        return "mp3"
    if value == "ogg":
        return "ogg"
    if value == "pcm":
        return "pcm"
    if value == "lpcm":
        return "lpcm"
    raise WsCommandError(
        "internal",
        f"Invalid response_format in DB: {value!r}",
        error_code="internal",
    )


def _row_to_item(row: CompanyVoiceProvider) -> CompanyVoiceProviderItem:
    provider = row.provider
    raw_sec = row.secrets
    meta_obj: CompanySecretsMetaDTO | None
    meta_obj = secrets_dict_to_meta(
        secrets=dict(raw_sec) if raw_sec else None,
        provider=provider,
    )
    return CompanyVoiceProviderItem(
        kind=_item_kind(row.kind),
        provider=provider,
        model=row.model,
        voice=row.voice,
        language=row.language,
        sample_rate=row.sample_rate,
        threshold=row.threshold,
        response_format=_response_format(row.response_format),
        secrets_meta=meta_obj,
    )


def _credential_providers_needing_optional_model(provider: str) -> bool:
    return provider in ("yandex", "sber")


@router.get("", response_model=CompanyVoiceProvidersResponse)
async def list_company_voice_providers(
    company_id: str,
    di: Di,
) -> CompanyVoiceProvidersResponse:
    """Список per-company override-ов провайдеров речи (stt/tts)."""
    user = require_context().user
    await _ensure_user_can_read_company(di, user, company_id)
    rows = await CompanyVoiceProvider.list_by_kind_for_company_asc(
        company_id=company_id
    )
    items = [_row_to_item(row) for row in rows if row.kind != "vad"]
    return CompanyVoiceProvidersResponse(
        company_id=company_id,
        items=items,
    )


@router.put("/{kind}", response_model=CompanyVoiceProviderItem)
async def upsert_company_voice_provider(
    company_id: str,
    kind: str,
    payload: CompanyVoiceProviderUpsertRequest,
    request: Request,
    di: Di,
) -> CompanyVoiceProviderItem:
    """Создать/обновить override для конкретного kind-а."""
    user = require_context().user
    await _ensure_user_can_manage_company(di, user, company_id)
    _reject_vad_path_kind(kind)
    voice_kind = _validate_kind(kind)
    _validate_provider(voice_kind, payload.provider)
    brand = resolve_brand_or_primary(request.headers.get("host"))
    voice_product_name = brand.voice_product_name

    effective_model = payload.model
    if effective_model == "":
        effective_model = None

    if payload.provider == "litserve":
        await _validate_model_for_voice(
            kind=voice_kind,
            provider=payload.provider,
            model_value=effective_model,
            voice_product_name=voice_product_name,
        )
    elif payload.provider == "cloud_ru":
        await _validate_model_for_voice(
            kind=voice_kind,
            provider=payload.provider,
            model_value=effective_model,
            voice_product_name=voice_product_name,
        )
    elif _credential_providers_needing_optional_model(payload.provider):
        if effective_model is not None:
            await _validate_model_for_voice(
                kind=voice_kind,
                provider=payload.provider,
                model_value=effective_model,
                voice_product_name=voice_product_name,
            )

    existing = await CompanyVoiceProvider.by_kind(
        company_id=company_id, kind=voice_kind
    )
    secrets_arg: SecretsPatchValue
    secrets_explicit = "secrets" in payload.model_fields_set
    allowed = frozenset(allowed_secret_keys(voice_kind, payload.provider))

    if not secrets_explicit:
        secrets_arg = unset_secrets_sentinel()
    elif payload.secrets is None:
        secrets_arg = None
    elif len(payload.secrets) == 0:
        secrets_arg = unset_secrets_sentinel()
    else:
        try:
            existing_secrets: dict[str, str] | None = None
            if existing is not None and existing.secrets:
                existing_secrets = dict(existing.secrets)
            merged = merge_secrets(
                existing=existing_secrets,
                patch=payload.secrets,
                allowed_keys=allowed,
            )
        except ValueError as exc:
            raise_invalid(exc)
        secrets_arg = merged if merged else None

    row = await CompanyVoiceProvider.upsert_by_kind(
        company_id=company_id,
        kind=voice_kind,
        provider=payload.provider,
        model=effective_model,
        voice=payload.voice,
        language=payload.language,
        sample_rate=payload.sample_rate,
        threshold=payload.threshold,
        response_format=payload.response_format,
        secrets=secrets_arg,
    )
    invalidate_voice_company_overrides_cache(company_id=company_id)
    logger.info(
        "frontend.company_voice_provider_upserted",
        company_id=company_id,
        voice_kind=voice_kind,
        provider=payload.provider,
        actor_user_id=user.user_id,
    )
    return _row_to_item(row)


@router.delete("/{kind}")
async def delete_company_voice_provider(
    company_id: str,
    kind: str,
    di: Di,
) -> dict[str, bool]:
    """Снять per-company override (вернуть kind на deployment-default)."""
    user = require_context().user
    await _ensure_user_can_manage_company(di, user, company_id)
    _reject_vad_path_kind(kind)
    voice_kind = _validate_kind(kind)
    deleted = await CompanyVoiceProvider.delete_by_company_kind(
        company_id=company_id, kind=voice_kind
    )
    invalidate_voice_company_overrides_cache(company_id=company_id)
    logger.info(
        "frontend.company_voice_provider_deleted",
        company_id=company_id,
        voice_kind=voice_kind,
        deleted=deleted,
        actor_user_id=user.user_id,
    )
    return {"deleted": deleted}
