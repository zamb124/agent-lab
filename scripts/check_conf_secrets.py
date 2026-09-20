#!/usr/bin/env python3
"""
CI-gate: в коммитимом `conf.json` нет секретов.

Значения ключей, похожих на секрет (`*api_key`, `*secret`, `*token`, `*password`,
`*private_key`), обязаны быть плейсхолдером (`YOUR_*`, `ВСТАВИТЬ_*`, пустая строка,
`@var:` ссылка) — реальные значения живут в `conf.local.json` (gitignored) или ENV/Helm.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONF_PATH = REPO_ROOT / "conf.json"
SECRET_KEY_RE = re.compile(r"(api_key|secret|token|password|passwd|private_key)$", re.IGNORECASE)
PLACEHOLDER_PREFIXES: tuple[str, ...] = ("YOUR_", "ВСТАВИТЬ_", "@var:")
# Дефолт dev coturn из docker-compose-dev.yaml (`--static-auth-secret=${TURN_SECRET:-turnsecret}`), не прод-секрет.
ALLOWED_PATHS: frozenset[str] = frozenset({"calls.turn_secret"})


def _walk(value: object, path: list[str], hits: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _walk(child, [*path, str(key)], hits)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk(child, [*path, str(index)], hits)
    elif isinstance(value, str):
        key = path[-1] if path else ""
        dotted = ".".join(path)
        if not SECRET_KEY_RE.search(key) or dotted in ALLOWED_PATHS:
            return
        if value == "" or value.startswith(PLACEHOLDER_PREFIXES):
            return
        hits.append(dotted)


def main() -> int:
    conf = json.loads(CONF_PATH.read_text(encoding="utf-8"))
    hits: list[str] = []
    _walk(conf, [], hits)
    if hits:
        print("check_conf_secrets: FAIL — в conf.json значения секретов должны быть плейсхолдерами YOUR_*:")
        for dotted in hits:
            print(f"  {dotted}")
        return 1
    print("check_conf_secrets: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
