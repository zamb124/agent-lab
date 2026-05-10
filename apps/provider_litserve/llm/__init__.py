"""Локальные HF causal LM для provider_litserve."""

from apps.provider_litserve.llm.local_causal_lm import ensure_local_causal_lm

__all__ = ["ensure_local_causal_lm"]
