#!/usr/bin/env python3
"""
CI-gate: запись в доменный Redis только с TTL.

Проверяет:
- RedisClient.set(...) в core/ и apps/ всегда с keyword ttl=
- RedisClient.rpush(...) всегда с keyword ttl_seconds=
- Новые redis.from_url / Redis.from_url только в allowlist (TaskIQ, locks, invites, WS).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from scripts.gates.kit import REPO_ROOT

SCAN_ROOTS: tuple[Path, ...] = (
    REPO_ROOT / "core",
    REPO_ROOT / "apps",
)

REDIS_FROM_URL_ALLOWLIST: frozenset[str] = frozenset(
    {
        "core/clients/redis_from_url.py",
    }
)

SKIP_DIR_NAMES: frozenset[str] = frozenset(
    {
        "vendor",
        "__pycache__",
    }
)

REDIS_IMPORT_MARKERS: tuple[str, ...] = (
    "redis.from_url",
    "Redis.from_url",
    "aioredis.from_url",
    "redis_async.Redis.from_url",
)


def _should_scan(path: Path) -> bool:
    return not any(part in SKIP_DIR_NAMES for part in path.parts)


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _call_has_keyword(call: ast.Call, keyword: str) -> bool:
    return any(arg.arg == keyword for arg in call.keywords)


def _call_has_expiration_keyword(call: ast.Call) -> bool:
    return _call_has_keyword(call, "ttl") or _call_has_keyword(call, "ex")


def _is_domain_redis_set(call: ast.Call) -> bool:
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != "set":
        return False
    value = func.value
    if isinstance(value, ast.Name):
        return value.id in {"redis_client", "_redis", "_redis_client", "redis"}
    if isinstance(value, ast.Attribute) and value.attr in {"_redis", "redis_client"}:
        return True
    if isinstance(value, ast.Call):
        inner = value.func
        if isinstance(inner, ast.Name) and inner.id == "_client":
            return True
    return False


def _is_domain_redis_rpush(call: ast.Call) -> bool:
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != "rpush":
        return False
    value = func.value
    if isinstance(value, ast.Name):
        return value.id in {"redis_client", "_redis", "_redis_client"}
    return False


def _check_python_file(path: Path) -> list[str]:
    rel = _relative(path)
    errors: list[str] = []
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        print(f"check_redis_ttl_canon: skip unreadable {rel}: {exc}", file=sys.stderr)
        return []
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError as exc:
        print(f"check_redis_ttl_canon: skip unparseable {rel}: {exc}", file=sys.stderr)
        return []
    except RecursionError as exc:
        print(f"check_redis_ttl_canon: skip too-deep AST {rel}: {exc}", file=sys.stderr)
        return []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if _is_domain_redis_set(node) and not _call_has_expiration_keyword(node):
                lineno = node.lineno
                errors.append(f"{rel}:{lineno}: redis SET без ttl=/ex=")
            if _is_domain_redis_rpush(node) and not _call_has_keyword(node, "ttl_seconds"):
                lineno = node.lineno
                errors.append(f"{rel}:{lineno}: RedisClient.rpush без keyword ttl_seconds=")

    if rel not in REDIS_FROM_URL_ALLOWLIST:
        for marker in REDIS_IMPORT_MARKERS:
            if marker in source:
                errors.append(f"{rel}: прямой Redis client ({marker}) вне allowlist")
                break

    return errors


def main() -> int:
    errors: list[str] = []
    for root in SCAN_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if not _should_scan(path):
                continue
            errors.extend(_check_python_file(path))

    if errors:
        print("check_redis_ttl_canon: FAIL")
        for item in errors:
            print(f"  - {item}")
        return 1

    print("check_redis_ttl_canon: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
