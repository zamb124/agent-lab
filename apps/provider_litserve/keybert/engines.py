"""KeyBERT keyword extraction for LitServe (multilingual RU/EN)."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, ClassVar, Literal, cast

import torch
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from apps.provider_litserve.provider_litserve_http_schemas import (
    KeybertExtractResponseBody,
    KeybertKeywordItem,
)
from core.config.models import ProviderLitserveInfraConfig
from core.logging import get_logger
from core.types import JsonObject, JsonValue

Backend = Literal["placeholder", "keybert"]

logger = get_logger(__name__)

_RE_WORD = re.compile(r"\b[a-zA-Zа-яёА-ЯЁ][a-zA-Zа-яёА-ЯЁ0-9_\-]{2,}\b")


class KeybertExtractRequest(BaseModel):
    """Тело POST ``/v1/keybert``."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    model: str | None = None
    text: str = Field(..., min_length=1)
    top_n: int = Field(default=50, ge=1, le=256)
    keyphrase_ngram_range: tuple[int, int] = Field(default=(1, 3))
    use_mmr: bool = True
    diversity: float = Field(default=0.7, ge=0.0, le=1.0)


def build_keybert_api_pairs(cfg: ProviderLitserveInfraConfig) -> dict[str, str]:
    api = cfg.keybert_openai_model_id.strip()
    hf = cfg.keybert_model_id.strip()
    if not api or not hf:
        return {}
    return {api: hf}


def allowed_keybert_api_model_ids(cfg: ProviderLitserveInfraConfig) -> frozenset[str]:
    return frozenset(build_keybert_api_pairs(cfg).keys())


def resolve_keybert_hf_model_id(api_model_id: str, cfg: ProviderLitserveInfraConfig) -> str | None:
    normalized = api_model_id.strip()
    if not normalized:
        return None
    pairs = build_keybert_api_pairs(cfg)
    if normalized in pairs:
        return pairs[normalized]
    lower = normalized.lower()
    for api, hf in pairs.items():
        if api.lower() == lower:
            return hf
    return None


def parse_keybert_body(raw: BaseModel | JsonValue) -> KeybertExtractRequest:
    if isinstance(raw, BaseModel):
        raw_payload = raw.model_dump(exclude_none=True)
    else:
        raw_payload = raw
    if not isinstance(raw_payload, dict):
        raise HTTPException(status_code=422, detail="Тело запроса: ожидается JSON-объект")
    try:
        body = KeybertExtractRequest.model_validate(raw_payload)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()) from e
    return body


def placeholder_keybert_keywords(text: str, *, top_n: int) -> list[KeybertKeywordItem]:
    """TF fallback for tests and ``keybert_backend=placeholder``."""
    counts: Counter[str] = Counter()
    first: dict[str, str] = {}
    for match in _RE_WORD.finditer(text):
        word = match.group(0)
        key = word.lower()
        if len(key) < 3:
            continue
        counts[key] += 1
        if key not in first:
            first[key] = word
    max_count = max(counts.values()) if counts else 1
    items: list[KeybertKeywordItem] = []
    for key, count in counts.most_common(top_n):
        term = first.get(key, key)
        items.append(KeybertKeywordItem(term=term, score=float(count) / float(max_count)))
    return items


def _require_cuda_when_selected(device: str) -> None:
    if not device.startswith("cuda"):
        return
    if not torch.cuda.is_available():
        message = (
            "provider_litserve: CUDA device для KeyBERT недоступен (torch.cuda.is_available() == False); "
            "нужны драйвер NVIDIA на хосте и GPU в деплое litserve."
        )
        raise RuntimeError(message)


class LocalKeybertEngine:
    """KeyBERT с multilingual SentenceTransformer или placeholder TF."""

    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        self._cfg: ProviderLitserveInfraConfig = cfg
        self._backend: Backend = "placeholder"
        self._models: dict[str, Any] = {}
        self._device: str = "cpu"

    def setup(self, device: str | None) -> None:
        self._backend = self._cfg.keybert_backend
        if self._backend == "placeholder":
            self._models = {}
            return
        if not device:
            raise RuntimeError("LitServe: пустой device в setup()")
        self._device = device

    def extract(self, request: KeybertExtractRequest) -> KeybertExtractResponseBody:
        canonical_model = (
            request.model.strip()
            if request.model is not None and request.model.strip()
            else self._cfg.keybert_openai_model_id
        )
        hf_model_id = resolve_keybert_hf_model_id(canonical_model, self._cfg)
        if hf_model_id is None:
            detail: JsonObject = {"reason": "unknown_keybert_model", "model": canonical_model}
            if request.model is not None:
                detail["allowed"] = sorted(allowed_keybert_api_model_ids(self._cfg))
            raise HTTPException(status_code=422, detail=detail)

        text = request.text
        if len(text) > self._cfg.keybert_max_text_chars:
            raise HTTPException(
                status_code=422,
                detail={
                    "reason": "text_too_long",
                    "max_chars": self._cfg.keybert_max_text_chars,
                    "got": len(text),
                },
            )

        if self._backend == "placeholder":
            keywords = placeholder_keybert_keywords(text, top_n=request.top_n)
            return KeybertExtractResponseBody(model=canonical_model, keywords=keywords)

        model = self._ensure_keybert(hf_model_id)
        raw = cast(
            list[tuple[str, float]],
            model.extract_keywords(
                text,
                keyphrase_ngram_range=list(request.keyphrase_ngram_range),
                stop_words=None,
                top_n=request.top_n,
                use_mmr=request.use_mmr,
                diversity=request.diversity,
            ),
        )
        keywords = [
            KeybertKeywordItem(term=str(term), score=float(score))
            for term, score in raw
            if str(term).strip()
        ]
        return KeybertExtractResponseBody(model=canonical_model, keywords=keywords)

    def _ensure_keybert(self, hf_model_id: str) -> Any:
        if hf_model_id in self._models:
            return self._models[hf_model_id]
        _require_cuda_when_selected(self._device)
        from keybert import KeyBERT
        from sentence_transformers import SentenceTransformer

        logger.info("Loading KeyBERT embedding model '%s' on '%s'", hf_model_id, self._device)
        st_model = SentenceTransformer(hf_model_id, device=self._device)
        kw_model = KeyBERT(model=cast(Any, st_model))
        self._models[hf_model_id] = kw_model
        return kw_model
