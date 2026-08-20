"""Подпись запросов и уведомлений интернет-эквайринга Т-Банка (SHA-256 Token)."""

from collections.abc import Mapping
from hashlib import sha256

from core.types import JsonScalar, JsonValue

TINKOFF_ORDER_ID_MAX_LEN = 50
TINKOFF_TRANSACTION_SUFFIX_HEX_LEN = 12


def rubles_to_kopecks(amount: float) -> int:
    if amount <= 0:
        raise ValueError("amount must be positive")
    kopecks = round(amount * 100)
    if abs(amount * 100 - kopecks) > 1e-6:
        raise ValueError(f"amount must have at most 2 decimal places: {amount}")
    return kopecks


def kopecks_to_rubles(kopecks: int) -> float:
    if kopecks < 0:
        raise ValueError("kopecks must be non-negative")
    return kopecks / 100.0


def tinkoff_token_scalar(value: JsonScalar) -> str:
    if value is None:
        raise ValueError("tinkoff token scalar must not be null")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)
    return value


def compute_tinkoff_token(fields: Mapping[str, JsonValue], password: str) -> str:
    if password.strip() == "":
        raise ValueError("tinkoff terminal password is required")
    token_parts: dict[str, str] = {}
    for key, value in fields.items():
        if key in ("Token", "Password"):
            continue
        if value is None:
            continue
        if isinstance(value, dict | list):
            continue
        if isinstance(value, str | int | float | bool):
            token_parts[key] = tinkoff_token_scalar(value)
            continue
        raise ValueError(f"tinkoff token field {key} has unsupported type {type(value).__name__}")
    token_parts["Password"] = password
    concatenated = "".join(token_parts[key] for key in sorted(token_parts.keys()))
    return sha256(concatenated.encode("utf-8")).hexdigest()
