"""
Резолвер per-company AI настроек: capability → конкретный provider/model/api_key/base_url/cost_origin.

Источник правды — ``Company.metadata['ai_providers']`` (см. ``schema.py``). Если override
отсутствует — используется платформенный дефолт (``platform_defaults`` + конфиг RAG/voice).

cost_origin:

- ``company`` — компания платит сама (BYOK поверх платформенного provider, либо custom:<id>).
- ``platform`` — расход идёт через платформенные ключи и облагается биллингом как обычно.

Все функции — read-only; запись и шифрование секретов делает API слой.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field

from core.company_ai.crypto import decrypt_secret
from core.company_ai.platform_defaults import (
    platform_default_model,
)
from core.company_ai.schema import (
    CUSTOM_PROVIDER_REF_PREFIX,
    CUSTOM_PROVIDER_SLUG,
    AICapability,
    CompanyAIProviders,
    CompanyCustomOpenAICompatibleProvider,
    CompanyLLMOverride,
    CompanyRerankOverride,
    CompanyVoiceOverride,
)
from core.context import get_context
from core.logging import get_logger

logger = get_logger(__name__)


CostOrigin = str  # "platform" | "company"
COST_ORIGIN_PLATFORM: CostOrigin = "platform"
COST_ORIGIN_COMPANY: CostOrigin = "company"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ResolvedLLM(_FrozenModel):
    """Финальные параметры для ``get_llm`` + биллинг-метаданные."""

    provider: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    folder_id: Optional[str] = None
    extra_request_headers: Optional[dict[str, str]] = None
    cost_origin: CostOrigin = COST_ORIGIN_PLATFORM
    custom_provider_id: Optional[str] = None

    @computed_field  # type: ignore[misc]
    @property
    def billing_resource_name(self) -> str:
        if self.cost_origin == COST_ORIGIN_COMPANY:
            return "llm:byok"
        return f"llm:{self.model}"


class ResolvedEmbedding(_FrozenModel):
    """Финальные параметры embedding HTTP-клиента."""

    provider: str
    model: str
    base_url: str
    api_key: Optional[str] = None
    extra_request_headers: Optional[dict[str, str]] = None
    cost_origin: CostOrigin = COST_ORIGIN_PLATFORM
    custom_provider_id: Optional[str] = None
    dimension: Optional[int] = None
    mrl_output_dimension: Optional[int] = None

    @computed_field  # type: ignore[misc]
    @property
    def billing_resource_name(self) -> str:
        if self.cost_origin == COST_ORIGIN_COMPANY:
            return "embedding:byok"
        return f"embedding:{self.model}"


class ResolvedRerank(_FrozenModel):
    """Политика реранка после применения company override."""

    enabled: bool
    url: Optional[str] = None
    api_key: Optional[str] = None
    extra_request_headers: Optional[dict[str, str]] = None
    cost_origin: CostOrigin = COST_ORIGIN_PLATFORM
    billing_resource_id: str = "rerank"
    custom_provider_id: Optional[str] = None

    @computed_field  # type: ignore[misc]
    @property
    def billing_resource_name(self) -> str:
        if self.cost_origin == COST_ORIGIN_COMPANY:
            return "rerank:byok"
        return f"rerank:{self.billing_resource_id}"


class ResolvedVoice(_FrozenModel):
    """Резолв провайдера речи (STT/TTS/VAD)."""

    provider: str
    model: Optional[str] = None
    voice: Optional[str] = None
    language: Optional[str] = None
    sample_rate: Optional[int] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    folder_id: Optional[str] = None
    extra_request_headers: Optional[dict[str, str]] = None
    cost_origin: CostOrigin = COST_ORIGIN_PLATFORM
    custom_provider_id: Optional[str] = None


def load_company_ai_providers() -> CompanyAIProviders:
    """Читает ``ai_providers`` из активной компании контекста; пусто если контекст не задан."""
    ctx = get_context()
    if ctx is None or ctx.active_company is None:
        return CompanyAIProviders()
    metadata = getattr(ctx.active_company, "metadata", None) or {}
    return CompanyAIProviders.from_metadata(metadata)


def _resolve_custom_provider(
    aip: CompanyAIProviders, ref: str
) -> CompanyCustomOpenAICompatibleProvider:
    if not ref.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        raise ValueError(f"_resolve_custom_provider: ref должен начинаться с custom:, получено {ref!r}")
    cid = ref[len(CUSTOM_PROVIDER_REF_PREFIX) :]
    return aip.find_custom(cid)


def _decrypt_or_none(token: Optional[str]) -> Optional[str]:
    if token is None or not str(token).strip():
        return None
    return decrypt_secret(token)


def resolve_llm_for_capability(
    capability: AICapability,
    *,
    fallback_provider: Optional[str] = None,
    fallback_model: Optional[str] = None,
) -> Optional[ResolvedLLM]:
    """
    Резолв LLM-капасити: возвращает ResolvedLLM или None если у компании нет override
    и платформа сама задаёт provider/model на месте вызова (например LLM_CHAT в bundle).

    Контракт: при наличии company override capability возвращается всегда; при отсутствии —
    None (вызывающий код использует свои дефолты).
    """
    if capability not in {
        AICapability.LLM_CHAT,
        AICapability.LLM_SUMMARIZE,
        AICapability.LLM_FORMAT_MARKDOWN,
        AICapability.LLM_CODEGEN,
        AICapability.LLM_VISION,
        AICapability.IMAGE_GEN,
    }:
        raise ValueError(f"resolve_llm_for_capability: capability {capability} не LLM-типа")

    aip = load_company_ai_providers()
    override = aip.get_capability_override(capability)
    if override is None:
        if fallback_provider and fallback_model:
            return ResolvedLLM(
                provider=fallback_provider,
                model=fallback_model,
                cost_origin=COST_ORIGIN_PLATFORM,
            )
        return None

    if not isinstance(override, CompanyLLMOverride):
        raise TypeError(
            f"capability {capability} ожидает CompanyLLMOverride, получено {type(override).__name__}"
        )

    if override.provider.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        custom = _resolve_custom_provider(aip, override.provider)
        model = (
            override.model
            or custom.model_by_capability.get(capability.value)
            or fallback_model
        )
        if not model or not str(model).strip():
            raise ValueError(
                f"capability {capability.value}: для custom_provider {custom.id!r} не задана "
                f"модель (model_by_capability[{capability.value}] или override.model)"
            )
        return ResolvedLLM(
            provider=CUSTOM_PROVIDER_SLUG,
            model=str(model).strip(),
            api_key=decrypt_secret(custom.api_key_encrypted),
            base_url=custom.base_url,
            extra_request_headers=dict(custom.extra_request_headers or {}) or None,
            cost_origin=COST_ORIGIN_COMPANY,
            custom_provider_id=custom.id,
        )

    api_key = _decrypt_or_none(override.api_key_encrypted)
    has_byok = bool(api_key) or bool(override.base_url)
    cost_origin = COST_ORIGIN_COMPANY if has_byok else COST_ORIGIN_PLATFORM

    model = override.model or platform_default_model(capability, override.provider) or fallback_model
    if not model or not str(model).strip():
        raise ValueError(
            f"capability {capability.value}: не удалось определить model "
            f"для provider {override.provider!r} (нет в platform_defaults и override.model пуст)"
        )

    return ResolvedLLM(
        provider=override.provider,
        model=str(model).strip(),
        api_key=api_key,
        base_url=override.base_url,
        folder_id=override.folder_id,
        extra_request_headers=dict(override.extra_request_headers or {}) or None,
        cost_origin=cost_origin,
        custom_provider_id=None,
    )


def resolve_embedding_for_company() -> Optional[ResolvedEmbedding]:
    """Резолв embedding override (provider + опц. ключ + URL); None если override не задан."""
    aip = load_company_ai_providers()
    if aip.embedding is None:
        return None
    ov = aip.embedding

    if ov.provider.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        custom = _resolve_custom_provider(aip, ov.provider)
        model = custom.model_by_capability.get(AICapability.EMBEDDING.value)
        if not model:
            raise ValueError(
                f"capability=embedding: custom_provider {custom.id!r} не задал model_by_capability['embedding']"
            )
        return ResolvedEmbedding(
            provider=CUSTOM_PROVIDER_SLUG,
            model=str(model).strip(),
            base_url=custom.base_url,
            api_key=decrypt_secret(custom.api_key_encrypted),
            extra_request_headers=dict(custom.extra_request_headers or {}) or None,
            cost_origin=COST_ORIGIN_COMPANY,
            custom_provider_id=custom.id,
        )

    api_key = _decrypt_or_none(ov.api_key_encrypted)
    has_byok = bool(api_key) or bool(ov.base_url)
    cost_origin = COST_ORIGIN_COMPANY if has_byok else COST_ORIGIN_PLATFORM

    return ResolvedEmbedding(
        provider=ov.provider,
        model="",
        base_url=ov.base_url or "",
        api_key=api_key,
        extra_request_headers=dict(ov.extra_request_headers or {}) or None,
        cost_origin=cost_origin,
        custom_provider_id=None,
    )


def resolve_rerank_for_company() -> Optional[ResolvedRerank]:
    """
    Резолв rerank override.

    Возвращает None если ``CompanyRerankOverride`` не задан (использовать глобальные настройки),
    либо ``ResolvedRerank(enabled=False)`` для policy=none, либо параметры HTTP-клиента.
    """
    aip = load_company_ai_providers()
    ov: Optional[CompanyRerankOverride] = aip.rerank
    if ov is None:
        return None

    pol = ov.policy
    if pol == "inherit":
        return None
    if pol == "none":
        return ResolvedRerank(
            enabled=False,
            url=None,
            api_key=None,
            extra_request_headers=None,
            cost_origin=COST_ORIGIN_PLATFORM,
        )
    if pol == "provider_litserve":
        return ResolvedRerank(
            enabled=True,
            url=None,
            api_key=None,
            extra_request_headers=None,
            cost_origin=COST_ORIGIN_PLATFORM,
        )
    if pol.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        custom = _resolve_custom_provider(aip, pol)
        if not custom.rerank_path:
            raise ValueError(
                f"rerank: custom_provider {custom.id!r} не задал rerank_path"
            )
        url = custom.base_url.rstrip("/") + custom.rerank_path
        return ResolvedRerank(
            enabled=True,
            url=url,
            api_key=decrypt_secret(custom.api_key_encrypted),
            extra_request_headers=dict(custom.extra_request_headers or {}) or None,
            cost_origin=COST_ORIGIN_COMPANY,
            billing_resource_id="rerank",
            custom_provider_id=custom.id,
        )
    raise ValueError(f"resolve_rerank_for_company: непредвиденный policy={pol!r}")


def resolve_voice_for_company(capability: AICapability) -> Optional[ResolvedVoice]:
    """Резолв voice override (stt/tts/vad). None если override не задан."""
    if capability not in (AICapability.VOICE_STT, AICapability.VOICE_TTS, AICapability.VOICE_VAD):
        raise ValueError(f"resolve_voice_for_company: capability {capability} не voice")
    aip = load_company_ai_providers()
    ov_raw = aip.get_capability_override(capability)
    if ov_raw is None:
        return None
    if not isinstance(ov_raw, CompanyVoiceOverride):
        raise TypeError(f"resolve_voice_for_company: override {capability.value} должен быть CompanyVoiceOverride")
    ov = ov_raw
    if ov.provider.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        if capability == AICapability.VOICE_VAD:
            raise ValueError("voice_vad: custom провайдеры не поддерживаются")
        custom = _resolve_custom_provider(aip, ov.provider)
        model = ov.model or custom.model_by_capability.get(capability.value)
        return ResolvedVoice(
            provider=CUSTOM_PROVIDER_SLUG,
            model=str(model).strip() if model else None,
            voice=ov.voice,
            language=ov.language,
            sample_rate=ov.sample_rate,
            api_key=decrypt_secret(custom.api_key_encrypted),
            base_url=custom.base_url,
            folder_id=ov.folder_id,
            extra_request_headers=dict(custom.extra_request_headers or {}) or None,
            cost_origin=COST_ORIGIN_COMPANY,
            custom_provider_id=custom.id,
        )

    api_key = _decrypt_or_none(ov.api_key_encrypted)
    has_byok = bool(api_key) or bool(ov.base_url)
    cost_origin = COST_ORIGIN_COMPANY if has_byok else COST_ORIGIN_PLATFORM
    return ResolvedVoice(
        provider=ov.provider,
        model=ov.model,
        voice=ov.voice,
        language=ov.language,
        sample_rate=ov.sample_rate,
        api_key=api_key,
        base_url=ov.base_url,
        folder_id=ov.folder_id,
        extra_request_headers=dict(ov.extra_request_headers or {}) or None,
        cost_origin=cost_origin,
    )


__all__ = [
    "COST_ORIGIN_COMPANY",
    "COST_ORIGIN_PLATFORM",
    "CostOrigin",
    "ResolvedEmbedding",
    "ResolvedLLM",
    "ResolvedRerank",
    "ResolvedVoice",
    "load_company_ai_providers",
    "resolve_embedding_for_company",
    "resolve_llm_for_capability",
    "resolve_rerank_for_company",
    "resolve_voice_for_company",
]
