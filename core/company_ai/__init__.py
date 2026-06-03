"""Per-company AI provider storage schema and secret helpers.

Runtime resolution and executable clients are public through ``core.ai``. This
package owns only the persisted ``Company.metadata['ai_providers']`` contract,
platform default metadata, and Fernet helpers used by API handlers.
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
    LLMContextPatch,
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
    "LLMContextPatch",
    "CUSTOM_PROVIDER_REF_PREFIX",
    "CUSTOM_PROVIDER_SLUG",
    "HUMANITEC_LLM_AUTO_MODEL",
    "HUMANITEC_LLM_PROVIDER",
    "METADATA_KEY",
    "PLATFORM_LLM_PROVIDERS",
    "decrypt_secret",
    "encrypt_secret",
    "mask_encrypted_secret",
    "mask_secret_plaintext",
    "platform_default_model",
    "platform_default_provider_for_capability",
]
