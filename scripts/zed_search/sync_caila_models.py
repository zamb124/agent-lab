#!/usr/bin/env python3
"""Синхронизирует модели Caila OpenRouter в Zed settings.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_API_URL = "https://caila.io/api/providers/openrouter/v1"
DEFAULT_MODELS_URL = "https://caila.io/api/openai/v1/models"
DEFAULT_PROVIDER = "Cailo igs"
DEFAULT_SETTINGS = Path.home() / ".config" / "zed" / "settings.json"

REASONING_PATTERNS = (
    r"o[134]-",
    r"gpt-5",
    r"claude-opus",
    r"claude-sonnet-4",
    r"deepseek-r",
    r"qwq",
    r"glm-4\.?5",
    r"glm-5",
    r"grok-",
    r"gemini-2\.5-pro",
    r"gemini-3",
    r"reasoning",
    r"think",
    r"r1",
    r"opus-4",
    r"sonar-reasoning",
    r"qwen3",
    r"nemotron",
)
VISION_PATTERNS = (
    r"vision",
    r"vl-",
    r"-vl",
    r"4o",
    r"gemini",
    r"claude",
    r"grok",
    r"pixtral",
    r"llava",
    r"qwen.*vl",
    r"nova",
    r"image",
    r"glm-4v",
    r"glm-4\.6v",
)


def _matches(patterns: tuple[str, ...], model_id: str) -> bool:
    model_id_lower = model_id.lower()
    return any(re.search(pattern, model_id_lower) for pattern in patterns)


def _zed_model_entry(model_id: str) -> dict[str, object]:
    reasoning = _matches(REASONING_PATTERNS, model_id)
    vision = _matches(VISION_PATTERNS, model_id)
    max_tokens = 200000
    max_output_tokens = 128000
    model_id_lower = model_id.lower()
    if "gpt-5" in model_id_lower or "o1" in model_id_lower or "o3" in model_id_lower:
        max_tokens = 272000
        max_output_tokens = 100000
    elif "glm-5" in model_id_lower:
        max_tokens = 1000000
        max_output_tokens = 131072
    elif "grok" in model_id_lower:
        max_tokens = 500000
        max_output_tokens = 32000
    elif "claude" in model_id_lower:
        max_tokens = 200000
        max_output_tokens = 128000
    entry: dict[str, object] = {
        "name": model_id,
        "max_tokens": max_tokens,
        "max_output_tokens": max_output_tokens,
        "max_completion_tokens": max_tokens,
        "capabilities": {
            "tools": True,
            "images": vision,
            "parallel_tool_calls": True,
            "prompt_cache_key": True,
            "chat_completions": True,
            "interleaved_reasoning": "claude" in model_id_lower or "anthropic" in model_id_lower,
            "max_tokens_parameter": False,
        },
    }
    if reasoning:
        entry["reasoning_effort"] = "max"
    return entry


def _fetch_model_ids(models_url: str, api_key: str) -> list[str]:
    request = urllib.request.Request(
        models_url,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"не удалось получить модели: HTTP {exc.code}") from exc
    if not isinstance(payload, dict):
        raise ValueError("ответ models должен быть объектом")
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("ответ models.data должен быть массивом")
    model_ids: list[str] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"models.data[{index}] должен быть объектом")
        model_id = item.get("id")
        if not isinstance(model_id, str) or model_id.strip() == "":
            raise ValueError(f"models.data[{index}].id обязателен")
        model_ids.append(model_id)
    return sorted(set(model_ids))


def _load_settings(settings_path: Path) -> tuple[str, dict[str, object]]:
    raw_text = settings_path.read_text(encoding="utf-8")
    json_lines = [line for line in raw_text.splitlines() if not line.lstrip().startswith("//")]
    settings = json.loads("\n".join(json_lines))
    if not isinstance(settings, dict):
        raise ValueError("settings.json должен содержать JSON-объект")
    return raw_text, settings


def _write_settings(settings_path: Path, settings: dict[str, object]) -> None:
    header = """// Zed settings
//
// For information on how to configure Zed, see the Zed
// documentation: https://zed.dev/docs/configuring-zed
//
// To see all of Zed's default settings without changing your
// custom settings, run zed: open default settings from the
// command palette (cmd-shift-p / ctrl-shift-p)
"""
    settings_path.write_text(
        header + json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def sync_caila_models(
    *,
    api_key: str,
    settings_path: Path,
    provider_name: str,
    api_url: str,
    models_url: str,
) -> int:
    if api_key.strip() == "":
        raise ValueError("api_key обязателен")
    if not settings_path.is_file():
        raise FileNotFoundError(f"settings не найден: {settings_path}")

    model_ids = _fetch_model_ids(models_url, api_key)
    raw_text, settings = _load_settings(settings_path)

    backup_path = settings_path.with_suffix(
        f".json.bak.sync-{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    )
    backup_path.write_text(raw_text, encoding="utf-8")

    language_models = settings.setdefault("language_models", {})
    if not isinstance(language_models, dict):
        raise ValueError("settings.language_models должен быть объектом")
    openai_compatible = language_models.setdefault("openai_compatible", {})
    if not isinstance(openai_compatible, dict):
        raise ValueError("settings.language_models.openai_compatible должен быть объектом")

    openai_compatible[provider_name] = {
        "api_url": api_url,
        "available_models": [_zed_model_entry(model_id) for model_id in model_ids],
    }
    _write_settings(settings_path, settings)
    print(
        f"[zed-search] Caila: {len(model_ids)} моделей → {provider_name} ({settings_path})",
        flush=True,
    )
    print(f"[zed-search] backup: {backup_path}", flush=True)
    return len(model_ids)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key", default="", help="Caila API key (или CAILA_API_KEY)")
    parser.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS)
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--models-url", default=DEFAULT_MODELS_URL)
    args = parser.parse_args()

    api_key = args.api_key.strip()
    if api_key == "":
        import os

        api_key = os.environ.get("CAILA_API_KEY", "").strip()
    if api_key == "":
        print("CAILA_API_KEY или --api-key обязателен", file=sys.stderr)
        return 1

    try:
        sync_caila_models(
            api_key=api_key,
            settings_path=args.settings,
            provider_name=args.provider,
            api_url=args.api_url,
            models_url=args.models_url,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
