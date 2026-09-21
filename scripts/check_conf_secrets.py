#!/usr/bin/env python3
"""
CI-gate: в коммитимом `conf.json` нет секретов.

Значения ключей, похожих на секрет (`*api_key`, `*secret`, `*token`, `*password`,
`*private_key`, `*access_key_id`, `*secret_access_key`), обязаны быть плейсхолдером
(`YOUR_*`, `ВСТАВИТЬ_*`, пустая строка, `@var:` ссылка) — реальные значения живут
в `conf.local.json` (gitignored) или ENV/Helm. Дополнительно любое строковое значение
с формой ключа провайдера (`sk-…`, `sk-or-…`, `agentset_…`, длинный hex/base64) — FAIL
независимо от имени ключа.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.types import JsonValue, parse_json_object  # noqa: E402

CONF_PATH = REPO_ROOT / "conf.json"
SECRET_KEY_RE = re.compile(
    r"(api_key|secret|token|password|passwd|private_key|access_key_id|secret_access_key)$",
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(
    r"^(sk-[A-Za-z0-9_-]{16,}|agentset_[A-Za-z0-9_-]{8,}|[0-9a-f]{32,}|[A-Za-z0-9+/]{40,}={0,2})$"
)
PLACEHOLDER_PREFIXES: tuple[str, ...] = ("YOUR_", "ВСТАВИТЬ_", "@var:")
# Дефолт dev coturn из docker-compose-dev.yaml (`--static-auth-secret=${TURN_SECRET:-turnsecret}`), не прод-секрет.
ALLOWED_PATHS: frozenset[str] = frozenset({"calls.turn_secret"})


def _walk(value: JsonValue, path: list[str], hits: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _walk(child, [*path, str(key)], hits)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk(child, [*path, str(index)], hits)
    elif isinstance(value, str):
        key = path[-1] if path else ""
        dotted = ".".join(path)
        if dotted in ALLOWED_PATHS:
            return
        if value == "" or value.startswith(PLACEHOLDER_PREFIXES):
            return
        if SECRET_KEY_RE.search(key):
            hits.append(f"{dotted} (имя ключа похоже на секрет)")
            return
        if SECRET_VALUE_RE.match(value):
            hits.append(f"{dotted} (значение похоже на ключ провайдера)")


def main() -> int:
    conf = parse_json_object(CONF_PATH.read_text(encoding="utf-8"), str(CONF_PATH))
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
