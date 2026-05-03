#!/usr/bin/env python3
"""Собирает deploy/helm/agent-lab/files/app-conf.json из корневого conf.json и overlay.

Артефакт в .gitignore; Helm читает его через .Files.Get — перед helm lint/template/upgrade
без make k8s-* выполните этот скрипт или make render-helm-app-conf.

Канон структуры: только корневой conf.json. Overlay задаёт дельты для Kubernetes;
значение null в overlay удаляет ключ из результата (как JSON Merge Patch).

Использование:
  uv run python deploy/scripts/render_helm_app_conf.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any


def _deep_overlay(base: Any, overlay: Any) -> Any:
    if overlay is None:
        return base
    if not isinstance(base, dict) or not isinstance(overlay, dict):
        return overlay
    merged: dict[str, Any] = copy.deepcopy(base)
    for key, value in overlay.items():
        if value is None:
            merged.pop(key, None)
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_overlay(merged[key], value)
        else:
            merged[key] = value
    return merged


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    chart_files = repo_root / "deploy" / "helm" / "agent-lab" / "files"
    base_path = repo_root / "conf.json"
    overlay_path = chart_files / "app-conf.k8s-overlay.json"
    out_path = chart_files / "app-conf.json"

    if not base_path.is_file():
        raise SystemExit(f"Не найден канон конфигурации: {base_path}")
    if not overlay_path.is_file():
        raise SystemExit(f"Не найден overlay: {overlay_path}")

    base = json.loads(base_path.read_text(encoding="utf-8"))
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    merged = _deep_overlay(base, overlay)

    out_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {out_path.relative_to(repo_root)}", file=sys.stderr)


if __name__ == "__main__":
    main()
