"""First-class identity/profile source for the platform LLM context layer."""

from __future__ import annotations

import hashlib

from core.context import get_context
from core.llm_context.models import LLMContextBlock
from core.llm_context.sources import LLMContextSourceRequest
from core.models.context_models import Context
from core.types import JsonObject

LLM_CONTEXT_PROFILE_METADATA_KEY = "llm_context_profile"


class IdentityLLMContextProfileSource:
    """Collect explicit user/company/runtime profile facts from the active Context."""

    name: str = "profile.identity"

    async def collect(self, request: LLMContextSourceRequest) -> list[LLMContextBlock]:
        _ = request
        block = build_identity_llm_context_profile_block(get_context())
        return [block] if block is not None else []


def build_identity_llm_context_profile_block(context: Context | None) -> LLMContextBlock | None:
    """Build one stable profile block from explicit profile fields in ``Context``."""
    if context is None:
        return None

    sections: list[tuple[str, str]] = []
    user = context.user
    if user.bio and user.bio.strip():
        sections.append(("User bio", user.bio.strip()))
    user_profile = _metadata_profile(user.attributes)
    if user_profile:
        sections.append(("User profile", user_profile))

    company = context.active_company
    if company is not None:
        company_profile = _metadata_profile(company.metadata)
        if company_profile:
            sections.append(("Company profile", company_profile))

    runtime_profile = _metadata_profile(context.metadata)
    if runtime_profile:
        sections.append(("Runtime profile", runtime_profile))

    if not sections:
        return None

    content = "[Profile]\n" + "\n\n".join(
        f"{title}:\n{text}" for title, text in sections
    )
    company_id = company.company_id if company is not None else None
    stable_key = _stable_profile_key(
        user_id=user.user_id,
        company_id=company_id,
        content=content,
    )
    provenance: JsonObject = {
        "source": IdentityLLMContextProfileSource.name,
        "user_id": user.user_id,
    }
    if company_id is not None and company_id.strip():
        provenance["company_id"] = company_id.strip()
    return LLMContextBlock(
        kind="profile",
        budget_scope="profile",
        role="system",
        content=content,
        stable_key=stable_key,
        priority=100,
        provenance=provenance,
    )


def _metadata_profile(metadata: JsonObject) -> str | None:
    value = metadata.get(LLM_CONTEXT_PROFILE_METADATA_KEY)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{LLM_CONTEXT_PROFILE_METADATA_KEY} must be a string")
    profile = value.strip()
    return profile or None


def _stable_profile_key(
    *,
    user_id: str,
    company_id: str | None,
    content: str,
) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    user_part = _safe_key_part(user_id, "user_id")
    company_part = _safe_key_part(company_id, "company_id") if company_id is not None else "no-company"
    return f"profile:identity:{company_part}:{user_part}:{digest}"


def _safe_key_part(value: str, field_name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("_", "-") else "-" for ch in value)
    normalized = safe.strip("-_")[:48]
    if not normalized:
        raise ValueError(f"{field_name} must contain key-safe characters")
    return normalized


__all__ = [
    "IdentityLLMContextProfileSource",
    "LLM_CONTEXT_PROFILE_METADATA_KEY",
    "build_identity_llm_context_profile_block",
]
