"""Shared fixtures for tests/core (live LLM network tests)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import cast

import pytest
from _pytest.nodes import Item

from core.config import set_settings
from core.config.base import BaseSettings
from core.config.loader import get_config_paths, load_json_config, merge_configs
from core.types import JsonObject, require_json_object

__all__ = ["_live_tests_use_conf_local_llm_keys"]

_LIVE_PLACEHOLDER_API_KEYS = frozenset({"sk-test-key", "test-key", "placeholder"})
_LIVE_PLACEHOLDER_PREFIXES = ("YOUR_",)


def _merged_file_config() -> JsonObject:
    merged: JsonObject = {}
    for config_path in get_config_paths():
        layer = load_json_config(config_path, silent=True)
        if layer:
            merged = merge_configs(merged, layer)
    return merged


def _provider_env_api_key_name(provider: str) -> str:
    return f"LLM__{provider.upper()}__API_KEY"


def _is_placeholder_api_key(api_key: str) -> bool:
    stripped = api_key.strip()
    if not stripped:
        return True
    if stripped in _LIVE_PLACEHOLDER_API_KEYS:
        return True
    return stripped.startswith(_LIVE_PLACEHOLDER_PREFIXES)


def _reload_settings() -> None:
    set_settings(BaseSettings())


@pytest.fixture(autouse=True)
def _live_tests_use_conf_local_llm_keys(request: pytest.FixtureRequest) -> Iterator[None]:
    item = cast(Item, request.node)
    if item.get_closest_marker("network") is None:
        yield
        return

    merged = _merged_file_config()
    llm_value = merged.get("llm")
    if not isinstance(llm_value, dict):
        yield
        return
    llm_config = require_json_object(llm_value, "llm")

    saved_env: dict[str, str | None] = {}
    for provider, provider_value in llm_config.items():
        if not isinstance(provider_value, dict):
            continue
        provider_config = require_json_object(provider_value, f"llm.{provider}")
        api_key_value = provider_config.get("api_key")
        if not isinstance(api_key_value, str) or not api_key_value.strip():
            continue
        file_api_key = api_key_value.strip()
        if _is_placeholder_api_key(file_api_key):
            continue

        env_key = _provider_env_api_key_name(provider)
        current_env = os.environ.get(env_key)
        if current_env is None or _is_placeholder_api_key(current_env):
            saved_env[env_key] = current_env
            os.environ[env_key] = file_api_key

    _reload_settings()
    yield
    for env_key, previous in saved_env.items():
        if previous is None:
            _ = os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = previous
    _reload_settings()
