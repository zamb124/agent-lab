"""Env и idle TTL гостя code_agent. Reserved-ключи платформы нельзя перезаписать guest_env."""

from __future__ import annotations

import re
from collections.abc import Mapping

GUEST_IDLE_TTL_MIN = 1
GUEST_IDLE_TTL_MAX = 86400
GUEST_IDLE_TTL_DEFAULT = 60

CAPABILITY_CALL_PATH = "/capability-gateway/api/v1/capabilities/call"

_GUEST_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

_RESERVED_GUEST_ENV_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "XDG_CACHE_HOME",
        "LANG",
        "PYTHONUNBUFFERED",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONPATH",
        "PYTHONHOME",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "CAPABILITY_GATEWAY_URL",
        "GUEST_LISTEN_PORT",
    }
)

_RESERVED_GUEST_ENV_PREFIXES = ("OPENAI_", "CAPABILITY_", "PLATFORM_", "GUEST_")


def guest_env_key_is_valid(key: str) -> bool:
    return _GUEST_ENV_KEY_RE.fullmatch(key) is not None


def guest_env_key_is_reserved(key: str) -> bool:
    if key in _RESERVED_GUEST_ENV_KEYS:
        return True
    return any(key.startswith(prefix) for prefix in _RESERVED_GUEST_ENV_PREFIXES)


def guest_host_path(parent: Mapping[str, str]) -> str:
    """PATH процесса фермы. Пустой PATH не годится ни docker, ни inprocess."""
    path = parent.get("PATH")
    if path is None or path.strip() == "":
        raise RuntimeError("PATH is required for guest env")
    return path


def apply_inprocess_host_env(env: dict[str, str], parent: Mapping[str, str]) -> None:
    """inprocess копирует PATH и непустые HOME и LANG процесса фермы."""
    env["PATH"] = guest_host_path(parent)
    for key in ("HOME", "LANG"):
        value = parent.get(key)
        if value is not None and value.strip() != "":
            env[key] = value


def validate_guest_env(guest_env: dict[str, str]) -> dict[str, str]:
    validated: dict[str, str] = {}
    for key, value in guest_env.items():
        if _GUEST_ENV_KEY_RE.fullmatch(key) is None:
            raise ValueError(
                f"guest_env key {key!r} must match {_GUEST_ENV_KEY_RE.pattern}"
            )
        if guest_env_key_is_reserved(key):
            raise ValueError(f"guest_env key {key!r} is reserved for the platform")
        if value.strip() == "":
            raise ValueError(f"guest_env {key} must be a non-empty string")
        validated[key] = value
    return validated


def resolve_idle_ttl_seconds(
    value: int | None,
    *,
    farm_idle_ttl_seconds: int,
    farm_max_lifetime_seconds: int,
) -> int:
    if value is None:
        idle = farm_idle_ttl_seconds
    else:
        if value < GUEST_IDLE_TTL_MIN or value > GUEST_IDLE_TTL_MAX:
            raise ValueError(
                f"idle_ttl_seconds must be between {GUEST_IDLE_TTL_MIN} and {GUEST_IDLE_TTL_MAX}"
            )
        idle = value
    if idle > farm_max_lifetime_seconds:
        raise ValueError(
            f"idle_ttl_seconds {idle} exceeds farm max_lifetime_seconds {farm_max_lifetime_seconds}"
        )
    return idle
