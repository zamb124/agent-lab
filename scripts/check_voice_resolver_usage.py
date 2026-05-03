#!/usr/bin/env python3
"""CI-проверка: использование `voice_resolver` как единственной точки входа.

В `apps/**` и в `core/**` (кроме каталога `core/clients/**`) запрещён прямой
импорт конкретных классов STT/TTS/VAD-клиентов из
`core.clients.{stt,tts,vad}_client`. Получать клиента можно **только**
через `core.clients.voice_resolver.get_*_client(*, company_id, override)`.

Допустимые импорты вне `core/clients/**`:

* базы — `BaseSTTClient`, `BaseTTSClient`, `BaseVADClient`;
* DTO — `STTTranscriptionResult`, `TTSResult`, `VADSegment`,
  `AudioTranscriptionStatus`;
* контракт — `core.clients.speech_override.SpeechOverride` и его типы.

Запрещено: `LitserveSTTClient`, `CloudRuSTTClient`, `YandexSTTClient`,
`SberSTTClient`, `MockSTTClient`, `STTClientFactory`, и аналогичные для
TTS и VAD (`Litserve/CloudRu/Yandex/Sber/Mock/LocalSilero` + `*ClientFactory`).

Запускать: ``uv run python scripts/check_voice_resolver_usage.py``.
Интегрируется в ``make check-events-canon`` / ``make check-voice-resolver``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
APPS_ROOT = REPO_ROOT / "apps"
CORE_ROOT = REPO_ROOT / "core"

FORBIDDEN_NAMES: frozenset[str] = frozenset(
    {
        "LitserveSTTClient",
        "CloudRuSTTClient",
        "YandexSTTClient",
        "SberSTTClient",
        "MockSTTClient",
        "STTClientFactory",
        "LitserveTTSClient",
        "CloudRuTTSClient",
        "YandexTTSClient",
        "SberTTSClient",
        "MockTTSClient",
        "TTSClientFactory",
        "LitserveVADClient",
        "LocalSileroVADClient",
        "MockVADClient",
        "VADClientFactory",
    }
)

WATCHED_MODULES: frozenset[str] = frozenset(
    {
        "core.clients.stt_client",
        "core.clients.tts_client",
        "core.clients.vad_client",
    }
)


class Violation:
    __slots__ = ("path", "lineno", "name", "module")

    def __init__(self, *, path: Path, lineno: int, name: str, module: str) -> None:
        self.path = path
        self.lineno = lineno
        self.name = name
        self.module = module

    def __str__(self) -> str:
        rel = self.path.relative_to(REPO_ROOT)
        return (
            f"{rel}:{self.lineno}: forbidden direct import "
            f"`{self.name}` from `{self.module}` — use "
            f"`core.clients.voice_resolver.get_*_client(*, company_id, override)`"
        )


def _iter_python_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT)
        parts = set(rel.parts)
        if "__pycache__" in parts or "node_modules" in parts:
            continue
        yield path


def _is_whitelisted_core_clients(rel: Path) -> bool:
    parts = rel.parts
    return len(parts) >= 2 and parts[0] == "core" and parts[1] == "clients"


def _check_file(path: Path) -> list[Violation]:
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return []

    violations: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module not in WATCHED_MODULES:
                continue
            for alias in node.names:
                if alias.name in FORBIDDEN_NAMES:
                    violations.append(
                        Violation(
                            path=path,
                            lineno=node.lineno,
                            name=alias.name,
                            module=module,
                        )
                    )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in WATCHED_MODULES:
                    violations.append(
                        Violation(
                            path=path,
                            lineno=node.lineno,
                            name=alias.name,
                            module=alias.name,
                        )
                    )
    return violations


def main() -> int:
    roots_ok = True
    if not APPS_ROOT.is_dir():
        print(f"check_voice_resolver_usage: apps directory not found at {APPS_ROOT}")
        roots_ok = False
    if not CORE_ROOT.is_dir():
        print(f"check_voice_resolver_usage: core directory not found at {CORE_ROOT}")
        roots_ok = False
    if not roots_ok:
        return 1

    all_violations: list[Violation] = []

    for path in _iter_python_files(APPS_ROOT):
        all_violations.extend(_check_file(path))

    for path in _iter_python_files(CORE_ROOT):
        rel = path.relative_to(REPO_ROOT)
        if _is_whitelisted_core_clients(rel):
            continue
        all_violations.extend(_check_file(path))

    if not all_violations:
        print(
            "check_voice_resolver_usage: OK (no forbidden STT/TTS/VAD client "
            "factory imports in apps/** or core/** outside core/clients/**)"
        )
        return 0

    print("check_voice_resolver_usage: FAIL", file=sys.stderr)
    for v in all_violations:
        print(str(v), file=sys.stderr)
    print(
        "\nResolution: import `BaseSTTClient`/`BaseTTSClient`/`BaseVADClient` only "
        "(outside core/clients), and obtain instances via "
        "`core.clients.voice_resolver.get_*_client`.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
