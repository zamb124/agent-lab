"""Unit tests for OnlyOffice AI settings builder and Lara model refs."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.office.ai_settings import (
    IMAGE_AUTO_MODEL_ID,
    LARA_DOCUMENTS_MODEL_ID,
    ONLYOFFICE_AI_ACTION_KEYS,
    ONLYOFFICE_AI_BROWSER_CORS_ORIGINS,
    PLATFORM_AUTO_MODEL_ID,
    build_onlyoffice_ai_settings,
    parse_lara_branch_model_id,
)
from core.types import require_json_object


def test_parse_lara_branch_model_id() -> None:
    assert parse_lara_branch_model_id("lara:documents") == "documents"
    assert parse_lara_branch_model_id("lara:") is None
    assert parse_lara_branch_model_id("auto") is None


def test_onlyoffice_ai_browser_cors_origins_cover_cdn_and_ds() -> None:
    assert "https://onlyoffice.github.io" in ONLYOFFICE_AI_BROWSER_CORS_ORIGINS
    assert "https://onlyoffice.linnex.io" in ONLYOFFICE_AI_BROWSER_CORS_ORIGINS
    assert "https://onlyoffice.humanitec.ru" in ONLYOFFICE_AI_BROWSER_CORS_ORIGINS


def test_build_onlyoffice_ai_settings_fills_all_actions() -> None:
    settings = build_onlyoffice_ai_settings(
        llm_api_base_url="https://example.com/flows/api/v1/llm",
        proxy_url="https://example.com/flows/api/v1/llm/v1/proxy",
        provider_display_name="Platform LLMs",
        allowed_cors_origins=[
            "https://onlyoffice.github.io",
            "https://onlyoffice-plugins.github.io",
        ],
    )
    actions = require_json_object(settings["actions"], "aiSettings.actions")
    for action_key in ONLYOFFICE_AI_ACTION_KEYS:
        assert action_key in actions
        model_ref = require_json_object(actions[action_key], f"actions.{action_key}")
        assert isinstance(model_ref.get("model"), str) and model_ref["model"]
    assert actions["Chat"]["model"] == LARA_DOCUMENTS_MODEL_ID
    assert actions["ImageGeneration"]["model"] == IMAGE_AUTO_MODEL_ID
    assert actions["Summarization"]["model"] == PLATFORM_AUTO_MODEL_ID


def test_build_onlyoffice_ai_settings_rejects_trailing_v1() -> None:
    with pytest.raises(ValueError, match="must not include trailing /v1"):
        build_onlyoffice_ai_settings(
            llm_api_base_url="https://example.com/flows/api/v1/llm/v1",
            proxy_url="https://example.com/proxy",
            provider_display_name="X",
            allowed_cors_origins=["https://onlyoffice.github.io"],
        )


def test_fixture_matches_builder() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "office"
        / "fixtures"
        / "onlyoffice_ai_settings.json"
    )
    fixture = require_json_object(
        __import__("json").loads(fixture_path.read_text(encoding="utf-8")),
        "fixture",
    )
    built = build_onlyoffice_ai_settings(
        llm_api_base_url="https://example.com/flows/api/v1/llm",
        proxy_url="https://example.com/flows/api/v1/llm/v1/proxy",
        provider_display_name="Platform LLMs",
        allowed_cors_origins=[
            "https://onlyoffice.github.io",
            "https://onlyoffice-plugins.github.io",
        ],
    )
    assert fixture["actions"] == built["actions"]
    assert fixture["version"] == built["version"]
