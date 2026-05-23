from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BUNDLES_DIR = Path("apps/flows/bundles")


def _iter_llm_configs(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "llm" and isinstance(child, dict) and ("provider" in child or "model" in child):
                yield child
            yield from _iter_llm_configs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_llm_configs(child)


def test_all_bundle_llm_configs_use_humanitec_virtual_provider() -> None:
    offenders: list[str] = []

    for path in sorted(BUNDLES_DIR.rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for llm in _iter_llm_configs(payload):
            provider = llm.get("provider")
            model = llm.get("model")
            if provider != "humanitec_llm" or model != "auto":
                offenders.append(f"{path}: provider={provider!r}, model={model!r}")

    assert offenders == []
