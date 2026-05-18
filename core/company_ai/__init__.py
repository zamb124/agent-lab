"""
Per-company AI providers — единая централизованная схема.

Public API:
- ``CompanyAIProviders`` — Pydantic-схема под ``Company.metadata['ai_providers']``.
- ``AICapability`` — функциональная роль (LLM_CHAT / EMBEDDING / RERANK / VOICE_*).
- ``resolve_llm_for_capability(...)`` / ``resolve_embedding_for_company()`` /
  ``resolve_rerank_for_company()`` / ``resolve_voice_for_company(...)`` — финальные
  параметры для get_llm / EmbeddingService / RerankerHTTPClient / voice_resolver.
- ``CUSTOM_PROVIDER_SLUG`` — внутренний slug ``custom_openai_compatible`` для get_llm.
- ``encrypt_secret`` / ``decrypt_secret`` / ``mask_encrypted_secret`` — Fernet helpers (API).

Никаких dual-read / fallback на старые ключи: единственный канон —
``ai_providers`` под ``Company.metadata`` (см. schema.py).
"""

from core.company_ai.crypto import (
    decrypt_secret,
    encrypt_secret,
    mask_encrypted_secret,
    mask_secret_plaintext,
)
from core.company_ai.platform_defaults import (
    platform_default_model,
    platform_default_provider_for_capability,
)
from core.company_ai.resolver import (
    COST_ORIGIN_COMPANY,
    COST_ORIGIN_PLATFORM,
    CostOrigin,
    ResolvedEmbedding,
    ResolvedLLM,
    ResolvedRerank,
    ResolvedVoice,
    load_company_ai_providers,
    resolve_custom_llm_provider_ref,
    resolve_embedding_for_company,
    resolve_llm_for_capability,
    resolve_rerank_for_company,
    resolve_voice_for_company,
)
from core.company_ai.schema import (
    CUSTOM_PROVIDER_REF_PREFIX,
    CUSTOM_PROVIDER_SLUG,
    HUMANITEC_LLM_AUTO_MODEL,
    HUMANITEC_LLM_PROVIDER,
    METADATA_KEY,
    PLATFORM_LLM_PROVIDERS,
    AICapability,
    CapabilityLiteral,
    CompanyAIProviders,
    CompanyCustomOpenAICompatibleProvider,
    CompanyEmbeddingOverride,
    CompanyLLMOverride,
    CompanyRerankOverride,
    CompanyVoiceOverride,
)

__all__ = [
    "AICapability",
    "CapabilityLiteral",
    "CompanyAIProviders",
    "CompanyCustomOpenAICompatibleProvider",
    "CompanyEmbeddingOverride",
    "CompanyLLMOverride",
    "CompanyRerankOverride",
    "CompanyVoiceOverride",
    "COST_ORIGIN_COMPANY",
    "COST_ORIGIN_PLATFORM",
    "CostOrigin",
    "CUSTOM_PROVIDER_REF_PREFIX",
    "CUSTOM_PROVIDER_SLUG",
    "HUMANITEC_LLM_AUTO_MODEL",
    "HUMANITEC_LLM_PROVIDER",
    "METADATA_KEY",
    "PLATFORM_LLM_PROVIDERS",
    "ResolvedEmbedding",
    "ResolvedLLM",
    "ResolvedRerank",
    "ResolvedVoice",
    "decrypt_secret",
    "encrypt_secret",
    "load_company_ai_providers",
    "mask_encrypted_secret",
    "mask_secret_plaintext",
    "platform_default_model",
    "platform_default_provider_for_capability",
    "resolve_custom_llm_provider_ref",
    "resolve_embedding_for_company",
    "resolve_llm_for_capability",
    "resolve_rerank_for_company",
    "resolve_voice_for_company",
]
