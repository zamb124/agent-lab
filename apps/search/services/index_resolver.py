"""Resolve platform index provider tokens and index_ids."""

from __future__ import annotations

import re
from dataclasses import dataclass

from apps.search.config import SearchIndexProviderConfig
from core.search.models import MetaSearchRequest

_INDEX_PREFIX = "index:"
_SEARCH_INDEX_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


@dataclass(frozen=True)
class PreprocessedMetaSearchRequest:
    request: MetaSearchRequest
    index_ids: list[str]


def _parse_index_slug(raw: str) -> str:
    slug = raw.strip().lower()
    if not _SEARCH_INDEX_ID_RE.match(slug):
        raise ValueError(f"invalid search_index_id slug: {raw}")
    return slug


def preprocess_meta_search_request(
    request: MetaSearchRequest,
    index_config: SearchIndexProviderConfig,
) -> PreprocessedMetaSearchRequest:
    index_ids: list[str] = list(request.index_ids)
    normalized_providers: list[str] = []
    saw_index_provider = False

    for token in request.providers:
        if token.startswith(_INDEX_PREFIX):
            saw_index_provider = True
            payload = token[len(_INDEX_PREFIX) :]
            if not payload:
                raise ValueError("index provider token requires index ids after prefix")
            for part in payload.split(","):
                part = part.strip()
                if not part:
                    continue
                slug = _parse_index_slug(part)
                if slug not in index_ids:
                    index_ids.append(slug)
            normalized_providers.append("index")
            continue
        if token == "runet":
            saw_index_provider = True
            if "runet" not in index_ids:
                index_ids.append("runet")
            if "index" not in normalized_providers:
                normalized_providers.append("index")
            continue
        if token == "index":
            saw_index_provider = True
            if "index" not in normalized_providers:
                normalized_providers.append("index")
            continue
        if token not in normalized_providers:
            normalized_providers.append(token)

    if saw_index_provider and not index_ids:
        if not index_config.default_index_ids:
            raise ValueError("index_ids are required when index provider is selected")
        index_ids = list(index_config.default_index_ids)

    if not index_ids and "auto" in request.providers:
        if not index_config.default_index_ids:
            raise ValueError("index_ids are required when auto provider uses platform index")
        index_ids = list(index_config.default_index_ids)

    if len(index_ids) > index_config.max_indexes_per_request:
        raise ValueError(
            f"too many index_ids: {len(index_ids)} > {index_config.max_indexes_per_request}"
        )

    if not normalized_providers:
        normalized_providers = ["auto"]

    updated = request.model_copy(update={"providers": normalized_providers, "index_ids": index_ids})
    return PreprocessedMetaSearchRequest(request=updated, index_ids=index_ids)
