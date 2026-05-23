"""First-class identity/profile source for the platform LLM context layer."""

from __future__ import annotations

import hashlib
from typing import Any

from core.context import get_context
from core.llm_context.models import LLMContextBlock
from core.llm_context.sources import LLMContextSourceRequest
from core.models.context_models import Context

LLM_CONTEXT_PROFILE_METADATA_KEY = "llm_context_profile"


class IdentityLLMContextProfileSource:
    """Collect explicit user/company/runtime profile facts from the active Context."""

    name = "profile.identity"

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
    if user is not None:
        if user.bio and user.bio.strip():
            sections.append(("User bio", user.bio.strip()))
        user_profile = _metadata_profile(getattr(user, "attrs", None))
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
    stable_key = _stable_profile_key(
        user_id=getattr(user, "user_id", None),
        company_id=getattr(company, "company_id", None),
        content=content,
    )
    return LLMContextBlock(
        kind="profile",
        budget_scope="profile",
        role="system",
        content=content,
        stable_key=stable_key,
        priority=100,
        provenance={
            key: value
            for key, value in {
                "source": IdentityLLMContextProfileSource.name,
                "user_id": getattr(user, "user_id", None),
                "company_id": getattr(company, "company_id", None),
            }.items()
            if isinstance(value, str) and value.strip()
        },
    )


def _metadata_profile(metadata: Any) -> str | None:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get(LLM_CONTEXT_PROFILE_METADATA_KEY)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        text = value.get("content") or value.get("text") or value.get("summary")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None


def _stable_profile_key(
    *,
    user_id: str | None,
    company_id: str | None,
    content: str,
) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    user_part = _safe_key_part(user_id or "user")
    company_part = _safe_key_part(company_id or "company")
    return f"profile:identity:{company_part}:{user_part}:{digest}"


def _safe_key_part(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("_", "-") else "-" for ch in value)
    return safe.strip("-_")[:48] or "unknown"


__all__ = [
    "IdentityLLMContextProfileSource",
    "LLM_CONTEXT_PROFILE_METADATA_KEY",
    "build_identity_llm_context_profile_block",
]
