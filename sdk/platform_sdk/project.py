"""Локальный проект агента: lock, кэш схемы, тело публикации."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from platform_sdk.bundle import assemble_bundle
from platform_sdk.errors import usage_error
from platform_sdk.json_types import JsonObject, JsonValue, as_json, require_object

_PUBLISH_FIELDS = (
    "flow_id",
    "name",
    "description",
    "entry",
    "nodes",
    "edges",
    "variables",
    "tags",
    "branches",
    "triggers",
    "resources",
    "store_card_image_url",
    "speech",
    "interface",
    "employee",
)
_HASH_SUFFIXES = {".yaml", ".yml", ".json", ".md", ".py", ".js", ".ts", ".go", ".cs"}


def publish_body(bundle_dir: Path, *, base_version: str | None) -> JsonObject:
    assembled = assemble_bundle(bundle_dir)
    body: JsonObject = {}
    for field in _PUBLISH_FIELDS:
        if field in assembled:
            body[field] = assembled[field]
    if "edges" not in body:
        body["edges"] = []
    if "variables" not in body:
        body["variables"] = {}
    if base_version is not None:
        body["base_version"] = base_version
    return body


def lock_path(bundle_dir: Path) -> Path:
    return bundle_dir / ".platform" / "lock.json"


def read_lock(bundle_dir: Path) -> JsonObject:
    path = lock_path(bundle_dir)
    if not path.is_file():
        raise usage_error(f"No lock at {path}. Run platform pull or platform push after init.")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return require_object(as_json(loaded, "lock"), "lock")


def write_lock(bundle_dir: Path, lock: JsonObject) -> None:
    path = lock_path(bundle_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock["files"] = file_hashes(bundle_dir)
    path.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_hashes(bundle_dir: Path) -> JsonObject:
    hashes: JsonObject = {}
    for path in sorted(bundle_dir.rglob("*")):
        if not path.is_file() or ".platform" in path.parts:
            continue
        if path.suffix not in _HASH_SUFFIXES and path.name != "AGENTS.md":
            continue
        relative = path.relative_to(bundle_dir).as_posix()
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def schema_dir(bundle_dir: Path) -> Path:
    return bundle_dir / ".platform" / "schema"


def write_schema_cache(bundle_dir: Path, schema: JsonObject) -> None:
    target = schema_dir(bundle_dir)
    target.mkdir(parents=True, exist_ok=True)
    for name, document in schema.items():
        body = require_object(document, name)
        text = json.dumps(body, ensure_ascii=False, indent=2) + "\n"
        (target / f"{name}.schema.json").write_text(text, encoding="utf-8")
        if name == "flow_create":
            (target / "flow.schema.json").write_text(text, encoding="utf-8")


def read_flow_schema(bundle_dir: Path) -> JsonObject | None:
    path = schema_dir(bundle_dir) / "flow.schema.json"
    if not path.is_file():
        return None
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return require_object(as_json(loaded, "flow schema"), "flow schema")


def json_object(value: JsonValue, label: str) -> JsonObject:
    return require_object(value, label)
