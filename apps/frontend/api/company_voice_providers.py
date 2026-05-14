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

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from apps.frontend.api.voice_providers_catalog_helpers import (
    CompanySecretsMetaDTO,
    allowed_secret_keys,
    secrets_dict_to_meta,
)
from apps.frontend.dependencies import ContainerDep
from core.clients.speech_provider_catalog import (
    STT_TTS_PROVIDER_IDS,
    cloud_ru_stt_model_ids,
    cloud_ru_tts_model_ids,
)
from core.clients.voice_resolver import invalidate_company_overrides_cache
from core.config import get_settings
from core.db.company_voice_provider_secrets import merge_secrets, unset_secrets_sentinel
from core.db.repositories.company_voice_provider_repository import VoiceKind
from core.logging import get_logger
from core.models.identity_models import User

logger = get_logger(__name__)
router = APIRouter(
    prefix="/api/companies/{company_id}/voice-providers",
    tags=["frontend", "voice"],
)

_VOICE_KINDS: tuple[VoiceKind, ...] = ("stt", "tts")

_YANDEX_SPEECH_MODELS = ("general",)
_SBER_SPEECH_MODELS = ("general",)


class CompanyVoiceProviderItem(BaseModel):
    """Одна запись `company_voice_providers` (ответ GET/PUT без сырых секретов)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["stt", "tts"] = Field(description="Тип провайдера речи.")
    provider: str = Field(description="Имя провайдера.")
    model: Optional[str] = Field(default=None)
    voice: Optional[str] = Field(default=None)
    language: Optional[str] = Field(default=None)
    sample_rate: Optional[int] = Field(default=None, gt=0)
    threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    response_format: Optional[Literal["wav", "mp3", "ogg", "pcm", "lpcm"]] = Field(
        default=None
    )
    secrets_meta: Optional[CompanySecretsMetaDTO] = Field(default=None)


class CompanyVoiceProvidersResponse(BaseModel):
    """Список настроек речи компании (stt/tts)."""

    model_config = ConfigDict(extra="forbid")

    company_id: str = Field(description="ID компании.")
    items: list[CompanyVoiceProviderItem] = Field(default_factory=list)


class CompanyVoiceProviderUpsertRequest(BaseModel):
    """Тело PUT-запроса для одного kind-а."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, description="Имя провайдера речи.")
    model: Optional[str] = Field(default=None)
    voice: Optional[str] = Field(default=None)
    language: Optional[str] = Field(default=None)
    sample_rate: Optional[int] = Field(default=None, gt=0)
    threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    response_format: Optional[Literal["wav", "mp3", "ogg", "pcm", "lpcm"]] = Field(
        default=None
    )
    secrets: Optional[dict[str, Optional[str]]] = Field(
        default=None,
        description=(
            "Merge-patch для колонки `secrets`; если поля нет в JSON — сохранённые "
            "ключи не меняются; если `secrets: null` — колонка очищается; в объект patch "
            "`null`/`\"\"` по ключу удаляет ключ, непустая строка — задаёт значение."
        ),
    )


def _require_authenticated_user(request: Request) -> User:
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    return request.state.user


def _ensure_user_can_read_company(user: User, company_id: str) -> None:
    if company_id not in user.companies:
        raise HTTPException(
            status_code=403, detail="Доступ только участникам этой компании"
        )


def _ensure_user_can_manage_company(user: User, company_id: str) -> None:
    roles = user.companies.get(company_id, [])
    if not any(role in ("owner", "admin") for role in roles):
        raise HTTPException(
            status_code=403,
            detail="Изменять провайдеров речи могут только owner/admin компании",
        )


def _reject_vad_path_kind(kind: str) -> None:
    if kind == "vad":
        raise HTTPException(
            status_code=410,
            detail="VAD настраивается на уровне развёртывания; per-company override удалён.",
        )


def _validate_kind(kind: str) -> VoiceKind:
    if kind not in _VOICE_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"Неизвестный kind: {kind!r}. Допустимы: {', '.join(_VOICE_KINDS)}",
        )
    return kind  # type: ignore[return-value]


def _validate_provider(kind: VoiceKind, provider: str) -> None:
    allowed = STT_TTS_PROVIDER_IDS
    if provider not in allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Неизвестный provider {provider!r} для kind={kind!r}; "
                f"допустимы: {', '.join(sorted(allowed))}"
            ),
        )


def _validate_model_for_voice(
    *, kind: VoiceKind, provider: str, model_value: Optional[str], voice_value: Optional[str]
) -> None:
    """Если model задан — должен быть из каталога провайдера; пустое значение допустимо
    для всех провайдеров (резолвер `voice_resolver` подставит default из настроек)."""
    if provider != "litserve":
        if provider == "cloud_ru":
            if model_value is None or model_value == "":
                return
            allowed = cloud_ru_stt_model_ids() if kind == "stt" else cloud_ru_tts_model_ids()
            if model_value not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=f"model допустимо только одно из: {', '.join(allowed)}",
                )
            return
        if provider == "yandex":
            if model_value is None or model_value == "":
                return
            if model_value not in _YANDEX_SPEECH_MODELS:
                raise HTTPException(
                    status_code=400,
                    detail=f"model Yandex допустимо одно из: {', '.join(_YANDEX_SPEECH_MODELS)}",
                )
            return
        if provider == "sber":
            if model_value is None or model_value == "":
                return
            if model_value not in _SBER_SPEECH_MODELS:
                raise HTTPException(
                    status_code=400,
                    detail=f"model Sber допустимо одно из: {', '.join(_SBER_SPEECH_MODELS)}",
                )
            return
        return

    if model_value is None or model_value == "":
        return

    infra = get_settings().provider_litserve.infra
    if kind == "stt":
        allowed = frozenset(m.api_model_id for m in infra.stt_models)
    else:
        allowed = frozenset(m.api_model_id for m in infra.tts_models)

    if model_value not in allowed:
        raise HTTPException(status_code=400, detail=f"Неизвестная litserve модель: {model_value!r}")


def _row_to_item(row: object) -> CompanyVoiceProviderItem:
    provider = row.provider  # type: ignore[attr-defined]
    raw_sec = getattr(row, "secrets", None)
    meta_obj: CompanySecretsMetaDTO | None
    meta_obj = secrets_dict_to_meta(
        secrets=dict(raw_sec) if isinstance(raw_sec, dict) else None,
        provider=provider,
    )
    return CompanyVoiceProviderItem(
        kind=row.kind,  # type: ignore[attr-defined]
        provider=provider,
        model=row.model,  # type: ignore[attr-defined]
        voice=row.voice,  # type: ignore[attr-defined]
        language=row.language,  # type: ignore[attr-defined]
        sample_rate=row.sample_rate,  # type: ignore[attr-defined]
        threshold=row.threshold,  # type: ignore[attr-defined]
        response_format=row.response_format,  # type: ignore[attr-defined]
        secrets_meta=meta_obj,
    )


def _credential_providers_needing_optional_model(provider: str) -> bool:
    return provider in ("yandex", "sber")


@router.get("", response_model=CompanyVoiceProvidersResponse)
async def list_company_voice_providers(
    company_id: str,
    request: Request,
    container: ContainerDep,
) -> CompanyVoiceProvidersResponse:
    """Список per-company override-ов провайдеров речи (stt/tts)."""
    user = _require_authenticated_user(request)
    _ensure_user_can_read_company(user, company_id)
    rows = await container.company_voice_provider_repository.list_by_company(
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
    container: ContainerDep,
) -> CompanyVoiceProviderItem:
    """Создать/обновить override для конкретного kind-а."""
    user = _require_authenticated_user(request)
    _ensure_user_can_manage_company(user, company_id)
    _reject_vad_path_kind(kind)
    voice_kind = _validate_kind(kind)
    _validate_provider(voice_kind, payload.provider)

    effective_model = payload.model
    if effective_model == "":
        effective_model = None

    if payload.provider == "litserve":
        _validate_model_for_voice(
            kind=voice_kind,
            provider=payload.provider,
            model_value=effective_model,
            voice_value=payload.voice,
        )
    elif payload.provider == "cloud_ru":
        _validate_model_for_voice(
            kind=voice_kind,
            provider=payload.provider,
            model_value=effective_model,
            voice_value=payload.voice,
        )
    elif _credential_providers_needing_optional_model(payload.provider):
        if effective_model is not None:
            _validate_model_for_voice(
                kind=voice_kind,
                provider=payload.provider,
                model_value=effective_model,
                voice_value=payload.voice,
            )

    existing = await container.company_voice_provider_repository.get(
        company_id=company_id, kind=voice_kind
    )
    secrets_arg: dict[str, str] | None | object
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
            merged = merge_secrets(
                existing=dict(existing.secrets) if existing and existing.secrets else None,  # type: ignore[arg-type]
                patch=payload.secrets,
                allowed_keys=allowed,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        secrets_arg = merged if merged else None

    row = await container.company_voice_provider_repository.upsert(
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
    invalidate_company_overrides_cache(company_id=company_id)
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
    request: Request,
    container: ContainerDep,
) -> dict[str, bool]:
    """Снять per-company override (вернуть kind на deployment-default)."""
    user = _require_authenticated_user(request)
    _ensure_user_can_manage_company(user, company_id)
    _reject_vad_path_kind(kind)
    voice_kind = _validate_kind(kind)
    deleted = await container.company_voice_provider_repository.delete(
        company_id=company_id, kind=voice_kind
    )
    invalidate_company_overrides_cache(company_id=company_id)
    logger.info(
        "frontend.company_voice_provider_deleted",
        company_id=company_id,
        voice_kind=voice_kind,
        deleted=deleted,
        actor_user_id=user.user_id,
    )
    return {"deleted": deleted}
