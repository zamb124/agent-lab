"""Named RAG document indexing profiles from platform config."""

from __future__ import annotations

from core.config import get_settings
from core.rag_indexing_schema import IndexProfileConfig


def resolve_index_profile(key: str | None) -> IndexProfileConfig:
    if key is None or key == "default":
        return get_settings().rag.document_indexing
    profiles = get_settings().rag.index_profiles
    if key not in profiles:
        raise ValueError(f"unknown index profile key: {key}")
    return profiles[key]
