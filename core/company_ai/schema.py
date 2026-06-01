"""
Строгая Pydantic-схема per-company AI-настроек, хранится в ``Company.metadata['ai_providers']``.

Единый источник правды для:
- LLM (chat / summarize / format_markdown / codegen / vision / image_gen) — выбор провайдера и BYOK
- Embedding (RAG) — выбор провайдера
- Rerank (RAG) — политика
- Voice STT / TTS / VAD — провайдер и секреты

Кастомные OpenAI-совместимые провайдеры компании (vLLM / Ollama / прокси / шлюз) хранятся в
``custom_providers`` с уникальным slug-id; capability override может ссылаться на них как
``provider="custom:<id>"``.

Список платформенных провайдеров — единственный источник правды:
``core.clients.llm.model_routing.PLATFORM_LLM_PROVIDER_ORDER``.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.ai_provider_catalog import (
    PROVIDER_LITSERVE,
    RERANK_POLICY_INHERIT,
    RERANK_POLICY_NONE,
    AICapability,
    validate_platform_provider_for_capability,
)
from core.clients.llm.config import LLMCallConfig, validate_fallback_model_configs
from core.clients.llm.model_routing import (
    HUMANITEC_LLM_AUTO_MODEL,
    HUMANITEC_LLM_PROVIDER,
    PLATFORM_LLM_PROVIDER_ORDER,
    split_humanitec_llms_model_ref,
)
from core.llm_context.models import LLMContextPatch
from core.types import JsonObject, require_json_object

METADATA_KEY = "ai_providers"


# Платформенные slug-и LLM-провайдеров компании (без custom_openai_compatible — он внутренний
# и не выбирается компанией напрямую, только через custom:<id>). Источник правды — model_routing.
CUSTOM_PROVIDER_SLUG = "custom_openai_compatible"
PLATFORM_LLM_PROVIDERS: tuple[str, ...] = PLATFORM_LLM_PROVIDER_ORDER
"""Дублирование запрещено: меняйте только ``PLATFORM_LLM_PROVIDER_ORDER``."""

CUSTOM_PROVIDER_REF_PREFIX = "custom:"

_CAPABILITY_VALUES = tuple(c.value for c in AICapability)
CapabilityLiteral = Literal[
    "llm_chat",
    "llm_summarize",
    "llm_format_markdown",
    "llm_codegen",
    "llm_vision",
    "embedding",
    "rerank",
    "image_gen",
    "voice_stt",
    "voice_tts",
    "voice_vad",
]


def _is_custom_ref(value: str) -> bool:
    return value.startswith(CUSTOM_PROVIDER_REF_PREFIX)


def _custom_ref_id(value: str) -> str:
    if not _is_custom_ref(value):
        raise ValueError(f"Не custom provider ref: {value!r}")
    return value[len(CUSTOM_PROVIDER_REF_PREFIX) :].strip()


def _validate_provider_ref(
    value: str,
    *,
    allow_custom: bool = True,
    allowed_platform: tuple[str, ...] = PLATFORM_LLM_PROVIDERS,
) -> str:
    v = value.strip()
    if not v:
        raise ValueError("provider не может быть пустым")
    if _is_custom_ref(v):
        if not allow_custom:
            raise ValueError(f"custom provider не разрешён в этой capability: {v!r}")
        slug = v[len(CUSTOM_PROVIDER_REF_PREFIX) :]
        if not slug or not all(c.isalnum() or c in ("-", "_") for c in slug) or len(slug) > 32:
            raise ValueError(f"custom provider id невалиден: {slug!r} (a-z 0-9 _ -, длина 1..32)")
        return v
    if v not in allowed_platform:
        raise ValueError(
            f"provider {v!r} не входит в whitelist {sorted(allowed_platform)} и не custom:<id>"
        )
    return v


class CompanyLLMOverride(BaseModel):
    """Override LLM-провайдера для одной capability компании.

    - ``provider`` платформенный (см. ``PLATFORM_LLM_PROVIDERS``) или ``custom:<id>``.
    - ``api_key_encrypted`` / ``base_url`` имеют смысл только для платформенных провайдеров (BYOK).
      Для ``custom:<id>`` оба поля игнорируются — URL и ключ берутся из ``custom_providers[id]``.
    - ``model`` опционален и используется только для capability без жёстко фиксированной
      платформенной модели; иначе берётся ``platform_defaults`` или alias custom-провайдера.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    provider: str
    api_key_encrypted: str | None = None
    base_url: str | None = None
    folder_id: str | None = None
    extra_request_headers: dict[str, str] | None = None
    model: str | None = None
    fallback_models: list[LLMCallConfig] | None = Field(
        default=None,
        description=(
            "Явная company-level fallback policy для capability. Транспортные секреты "
            "внутри fallback запрещены, используйте custom:<id> для BYOK fallback."
        ),
    )

    @field_validator("provider")
    @classmethod
    def _v_provider(cls, v: str) -> str:
        return _validate_provider_ref(v, allow_custom=True)

    @field_validator("base_url")
    @classmethod
    def _v_base_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            return None
        if not (s.startswith("http://") or s.startswith("https://")):
            raise ValueError("base_url должен начинаться с http:// или https://")
        return s

    @model_validator(mode="after")
    def _v_byok_only_for_platform(self) -> "CompanyLLMOverride":
        if _is_custom_ref(self.provider):
            if self.api_key_encrypted or self.base_url or self.extra_request_headers:
                raise ValueError(
                    "Для provider=custom:<id> поля api_key_encrypted/base_url/extra_request_headers "
                    + "не используются — задайте их в custom_providers"
                )
        if self.provider == HUMANITEC_LLM_PROVIDER:
            if (
                self.api_key_encrypted
                or self.base_url
                or self.folder_id
                or self.extra_request_headers
            ):
                raise ValueError(
                    "provider=humanitec_llm — виртуальный платформенный провайдер; "
                    + "api_key_encrypted/base_url/folder_id/extra_request_headers не задаются"
                )
            if (
                self.model
                and self.model != HUMANITEC_LLM_AUTO_MODEL
                and split_humanitec_llms_model_ref(self.model) is None
            ):
                raise ValueError(
                    "provider=humanitec_llm поддерживает model='auto' или "
                    + "provider-prefixed free-pool модель '<provider>:<model_id>'"
                )
        self.fallback_models = validate_fallback_model_configs(self.fallback_models)
        for idx, fallback in enumerate(self.fallback_models or []):
            if fallback.provider == HUMANITEC_LLM_PROVIDER and (
                fallback.model != HUMANITEC_LLM_AUTO_MODEL
                and split_humanitec_llms_model_ref(fallback.model) is None
            ):
                raise ValueError(
                    f"fallback_models[{idx}]: provider=humanitec_llm поддерживает "
                    + "model='auto' или provider-prefixed free-pool модель '<provider>:<model_id>'"
                )
            if fallback.provider is not None:
                _ = _validate_provider_ref(fallback.provider, allow_custom=True)
            secret_fields = {
                "api_key": fallback.api_key,
                "base_url": fallback.base_url,
                "folder_id": fallback.folder_id,
                "extra_request_headers": fallback.extra_request_headers,
            }
            present_secret_fields = [
                name for name, value in secret_fields.items() if value is not None
            ]
            if present_secret_fields:
                raise ValueError(
                    f"fallback_models[{idx}]: поля {present_secret_fields} запрещены в "
                    + "company metadata; используйте platform provider без секрета или custom:<id>"
                )
        return self


class CompanyEmbeddingOverride(BaseModel):
    """Override embedding-провайдера компании с явной моделью и storage dimension."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    provider: str
    api_key_encrypted: str | None = None
    base_url: str | None = None
    extra_request_headers: dict[str, str] | None = None
    model: str
    dimension: int = Field(gt=0)
    mrl_output_dimension: int | None = Field(default=None, gt=0)

    @field_validator("provider")
    @classmethod
    def _v_provider(cls, v: str) -> str:
        s = v.strip()
        if _is_custom_ref(s):
            return _validate_provider_ref(s, allow_custom=True)
        return validate_platform_provider_for_capability(s, AICapability.EMBEDDING)

    @field_validator("model")
    @classmethod
    def _v_model(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("embedding.model не может быть пустым")
        return s

    @model_validator(mode="after")
    def _v_byok_only_for_platform(self) -> "CompanyEmbeddingOverride":
        if self.provider == HUMANITEC_LLM_PROVIDER:
            raise ValueError("provider=humanitec_llm не поддерживает embedding")
        if self.mrl_output_dimension is not None and self.mrl_output_dimension > self.dimension:
            raise ValueError("embedding.mrl_output_dimension не может превышать embedding.dimension")
        if _is_custom_ref(self.provider):
            if self.api_key_encrypted or self.base_url or self.extra_request_headers:
                raise ValueError(
                    "Для embedding provider=custom:<id> поля BYOK не используются"
                )
        return self


class CompanyRerankOverride(BaseModel):
    """Политика реранка компании.

    ``policy``:

    - ``inherit`` — использовать глобальный ``rag.reranker``.
    - ``none`` — реранк выключен для запросов компании.
    - ``provider_litserve`` — принудительно LitServe (URL берётся из ``provider_litserve.api.base_url``).
    - ``custom:<id>`` — кастомный провайдер с заданным ``rerank_path``.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    policy: str

    @field_validator("policy")
    @classmethod
    def _v_policy(cls, v: str) -> str:
        s = v.strip()
        if s in (RERANK_POLICY_INHERIT, RERANK_POLICY_NONE):
            return s
        if _is_custom_ref(s):
            return _validate_provider_ref(s, allow_custom=True)
        if s == PROVIDER_LITSERVE:
            return validate_platform_provider_for_capability(s, AICapability.RERANK)
        raise ValueError(
            f"rerank.policy {v!r}: ожидается inherit | none | {PROVIDER_LITSERVE} | custom:<id>"
        )


class CompanyVoiceOverride(BaseModel):
    """Override провайдера речи компании (один из stt/tts/vad)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    provider: str
    api_key_encrypted: str | None = None
    base_url: str | None = None
    folder_id: str | None = None
    extra_request_headers: dict[str, str] | None = None
    model: str | None = None
    voice: str | None = None
    language: str | None = None
    sample_rate: int | None = None

    @field_validator("provider")
    @classmethod
    def _v_provider(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("voice provider не может быть пустым")
        # Для voice разрешены платформенные литералы (litserve/cloud_ru/yandex/sber/silero_local/mock)
        # и custom:<id> (только для stt/tts).
        if _is_custom_ref(s):
            return _validate_provider_ref(s, allow_custom=True)
        if not all(c.isalnum() or c in ("-", "_") for c in s) or len(s) > 32:
            raise ValueError(f"voice provider {v!r} невалиден")
        return s


class CompanyCustomOpenAICompatibleProvider(BaseModel):
    """OpenAI-совместимый endpoint компании (vLLM / Ollama / прокси / корпоративный шлюз)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    id: Annotated[str, Field(min_length=1, max_length=32)]
    label: Annotated[str, Field(min_length=1, max_length=128)]
    base_url: str
    api_key_encrypted: str
    extra_request_headers: dict[str, str] | None = None
    extra_request_body: JsonObject | None = None
    rerank_path: str | None = None
    capabilities: list[CapabilityLiteral] = Field(default_factory=list)
    model_by_capability: dict[str, str] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _v_id(cls, v: str) -> str:
        s = v.strip()
        if not all(c.isalnum() or c in ("-", "_") for c in s):
            raise ValueError(f"custom provider id {v!r} невалиден (a-z A-Z 0-9 _ -)")
        return s

    @field_validator("base_url")
    @classmethod
    def _v_base_url(cls, v: str) -> str:
        s = v.strip()
        if not (s.startswith("http://") or s.startswith("https://")):
            raise ValueError("base_url должен начинаться с http:// или https://")
        return s

    @field_validator("rerank_path")
    @classmethod
    def _v_rerank_path(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            return None
        if not s.startswith("/"):
            raise ValueError("rerank_path должен начинаться с /")
        return s

    @model_validator(mode="after")
    def _v_consistency(self) -> "CompanyCustomOpenAICompatibleProvider":
        if "rerank" in self.capabilities and not self.rerank_path:
            raise ValueError("capabilities содержит 'rerank', но rerank_path не задан")
        for cap in self.model_by_capability.keys():
            if cap not in _CAPABILITY_VALUES:
                raise ValueError(f"model_by_capability: неизвестная capability {cap!r}")
        return self


class CompanyAIProviders(BaseModel):
    """Корневая схема ``Company.metadata['ai_providers']``."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    custom_providers: list[CompanyCustomOpenAICompatibleProvider] = Field(default_factory=list)

    llm_chat: CompanyLLMOverride | None = None
    llm_summarize: CompanyLLMOverride | None = None
    llm_format_markdown: CompanyLLMOverride | None = None
    llm_codegen: CompanyLLMOverride | None = None
    llm_vision: CompanyLLMOverride | None = None
    embedding: CompanyEmbeddingOverride | None = None
    rerank: CompanyRerankOverride | None = None
    llm_context: LLMContextPatch | None = None
    image_gen: CompanyLLMOverride | None = None
    voice_stt: CompanyVoiceOverride | None = None
    voice_tts: CompanyVoiceOverride | None = None
    voice_vad: CompanyVoiceOverride | None = None

    @model_validator(mode="after")
    def _v_unique_custom_ids_and_refs(self) -> "CompanyAIProviders":
        ids = [p.id for p in self.custom_providers]
        if len(ids) != len(set(ids)):
            dups = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"custom_providers: дубликаты id {dups}")
        custom_index = {p.id: p for p in self.custom_providers}

        for cap, ov in (
            ("llm_chat", self.llm_chat),
            ("llm_summarize", self.llm_summarize),
            ("llm_format_markdown", self.llm_format_markdown),
            ("llm_codegen", self.llm_codegen),
            ("llm_vision", self.llm_vision),
            ("image_gen", self.image_gen),
        ):
            if ov is None:
                continue
            self._check_provider_ref(ov.provider, capability=cap, custom_index=custom_index)
            for fallback in ov.fallback_models or []:
                if fallback.provider and _is_custom_ref(fallback.provider):
                    self._check_provider_ref(
                        fallback.provider,
                        capability=cap,
                        custom_index=custom_index,
                    )

        if self.embedding is not None:
            self._check_provider_ref(
                self.embedding.provider, capability="embedding", custom_index=custom_index
            )
        if self.rerank is not None:
            pol = self.rerank.policy
            if _is_custom_ref(pol):
                self._check_provider_ref(pol, capability="rerank", custom_index=custom_index)
        for cap, ov_v in (("voice_stt", self.voice_stt), ("voice_tts", self.voice_tts)):
            if ov_v is None:
                continue
            if _is_custom_ref(ov_v.provider):
                self._check_provider_ref(
                    ov_v.provider, capability=cap, custom_index=custom_index
                )
        if self.voice_vad is not None and _is_custom_ref(self.voice_vad.provider):
            raise ValueError("voice_vad: custom провайдеры не поддерживаются")

        return self

    @staticmethod
    def _check_provider_ref(
        ref: str,
        *,
        capability: str,
        custom_index: dict[str, CompanyCustomOpenAICompatibleProvider],
    ) -> None:
        if not _is_custom_ref(ref):
            _ = validate_platform_provider_for_capability(ref, AICapability(capability))
            return
        cid = _custom_ref_id(ref)
        if cid not in custom_index:
            raise ValueError(
                f"capability={capability}: ссылка {ref!r} не найдена в custom_providers"
            )
        prov = custom_index[cid]
        if capability not in prov.capabilities:
            raise ValueError(
                f"capability={capability}: custom_provider {cid!r} не поддерживает её "
                + f"(capabilities={prov.capabilities})"
            )

    @classmethod
    def from_metadata(cls, metadata: JsonObject) -> "CompanyAIProviders":
        """Парсит ``metadata['ai_providers']``; пустой/отсутствующий → пустая модель."""
        raw = metadata.get(METADATA_KEY)
        if raw is None:
            return cls()
        return cls.model_validate(
            require_json_object(raw, f"company.metadata[{METADATA_KEY!r}]")
        )

    def to_metadata_dict(self) -> JsonObject:
        """Сериализация для записи в ``Company.metadata[METADATA_KEY]``."""
        return require_json_object(
            self.model_dump(mode="json", exclude_none=True),
            "CompanyAIProviders.metadata",
        )

    def find_custom(self, custom_id: str) -> CompanyCustomOpenAICompatibleProvider:
        for p in self.custom_providers:
            if p.id == custom_id:
                return p
        raise KeyError(f"custom provider {custom_id!r} не найден")

    def get_capability_override(
        self, capability: AICapability
    ) -> CompanyLLMOverride | CompanyEmbeddingOverride | CompanyRerankOverride | CompanyVoiceOverride | None:
        match capability:
            case AICapability.LLM_CHAT:
                return self.llm_chat
            case AICapability.LLM_SUMMARIZE:
                return self.llm_summarize
            case AICapability.LLM_FORMAT_MARKDOWN:
                return self.llm_format_markdown
            case AICapability.LLM_CODEGEN:
                return self.llm_codegen
            case AICapability.LLM_VISION:
                return self.llm_vision
            case AICapability.EMBEDDING:
                return self.embedding
            case AICapability.RERANK:
                return self.rerank
            case AICapability.IMAGE_GEN:
                return self.image_gen
            case AICapability.VOICE_STT:
                return self.voice_stt
            case AICapability.VOICE_TTS:
                return self.voice_tts
            case AICapability.VOICE_VAD:
                return self.voice_vad


__all__ = [
    "AICapability",
    "CapabilityLiteral",
    "CompanyAIProviders",
    "CompanyCustomOpenAICompatibleProvider",
    "CompanyEmbeddingOverride",
    "CompanyLLMOverride",
    "LLMContextPatch",
    "CompanyRerankOverride",
    "CompanyVoiceOverride",
    "CUSTOM_PROVIDER_REF_PREFIX",
    "CUSTOM_PROVIDER_SLUG",
    "HUMANITEC_LLM_AUTO_MODEL",
    "HUMANITEC_LLM_PROVIDER",
    "METADATA_KEY",
    "PLATFORM_LLM_PROVIDERS",
]
