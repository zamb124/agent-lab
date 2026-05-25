"""Deterministic hashing for workflow projections."""

from __future__ import annotations

import hashlib
import json

from core.types import JsonObject


def canonical_json(value: JsonObject) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def hash_state_json(value: JsonObject) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
