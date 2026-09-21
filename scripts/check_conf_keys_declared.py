#!/usr/bin/env python3
"""
CI-gate: каждый ключ `conf.json` объявлен в Pydantic Settings.

Корневые ключи (кроме `services`) сверяются с `core.config.BaseSettings`; каждый слой
`services.<name>` сливается поверх корня и сверяется с Settings-классом сервиса
(`apps/<name>/config.py`, для `<svc>_worker` без своего config — `apps/<svc>/config.py`).
Сверка рекурсивная по `model_fields` вложенных моделей, поэтому ключ, который Pydantic
молча отбросил бы (`extra="ignore"` у вложенной модели), тоже ловится. Неизвестный
ключ = FAIL: конфиг без владельца в коде — это Zero-Guess нарушение.
"""

from __future__ import annotations

import importlib
import inspect
import sys
import types
from pathlib import Path
from typing import get_args, get_origin

from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.config.base import BaseSettings  # noqa: E402
from core.config.loader import load_json_config, merge_configs  # noqa: E402
from core.types import JsonObject, JsonValue, require_json_object  # noqa: E402


def _model_types(annotation: object) -> list[type[BaseModel]]:
    """Все Pydantic-модели, до которых можно дойти по аннотации (Optional, dict[str, M], list[M])."""
    if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
        return [annotation]
    origin = get_origin(annotation)
    if origin is None:
        return []
    if origin is types.UnionType:
        found: list[type[BaseModel]] = []
        for arg in get_args(annotation):
            found.extend(_model_types(arg))
        return found
    args = get_args(annotation)
    if origin is dict and len(args) == 2:
        return _model_types(args[1])
    if origin in (list, tuple, set, frozenset) and args:
        return _model_types(args[0])
    return []


def _is_mapping_annotation(annotation: object) -> bool:
    origin = get_origin(annotation)
    return origin is dict or any(get_origin(arg) is dict for arg in get_args(annotation))


def _check_object(model: type[BaseModel], payload: JsonObject, path: str, errors: list[str]) -> None:
    fields = model.model_fields
    by_alias = {field.alias: name for name, field in fields.items() if field.alias}
    for key, value in payload.items():
        name = key if key in fields else by_alias.get(key)
        if name is None:
            errors.append(f"{path}.{key}: не объявлен в {model.__module__}.{model.__name__}")
            continue
        field = fields[name]
        nested_models = _model_types(field.annotation)
        if not nested_models or not isinstance(value, dict):
            continue
        nested = nested_models[0]
        if _is_mapping_annotation(field.annotation):
            for entry_key, entry in value.items():
                if isinstance(entry, dict):
                    _check_object(nested, require_json_object(entry, f"{path}.{key}.{entry_key}"), f"{path}.{key}.{entry_key}", errors)
            continue
        _check_object(nested, require_json_object(value, f"{path}.{key}"), f"{path}.{key}", errors)


def _settings_class_for(layer: str) -> type[BaseSettings]:
    candidates = [f"apps.{layer}.config"]
    if layer.endswith("_worker"):
        candidates.append(f"apps.{layer.removesuffix('_worker')}.config")
    for module_name in candidates:
        if not (REPO_ROOT / module_name.replace(".", "/")).with_suffix(".py").exists():
            continue
        module = importlib.import_module(module_name)
        owned = [
            member
            for _, member in inspect.getmembers(module, inspect.isclass)
            if issubclass(member, BaseSettings) and member is not BaseSettings and member.__module__ == module_name
        ]
        if len(owned) != 1:
            raise SystemExit(f"{module_name}: ожидается ровно один класс Settings, найдено {len(owned)}")
        return owned[0]
    raise SystemExit(f"services.{layer}: нет apps/{layer}/config.py с классом Settings — слой конфига без владельца")


def main() -> int:
    conf = load_json_config(REPO_ROOT / "conf.json", silent=True)
    services_value: JsonValue = conf.get("services", {})
    services = require_json_object(services_value, "services")
    root_layer: JsonObject = {key: value for key, value in conf.items() if key != "services"}
    errors: list[str] = []
    _check_object(BaseSettings, root_layer, "conf", errors)
    for layer_name in sorted(services):
        settings_class = _settings_class_for(layer_name)
        layer = require_json_object(services[layer_name], f"services.{layer_name}")
        merged = merge_configs(root_layer, layer)
        _check_object(settings_class, merged, f"services.{layer_name}", errors)
    if errors:
        print("check_conf_keys_declared: FAIL — ключи conf.json без поля в Settings:")
        for error in errors:
            print(f"  {error}")
        return 1
    print(f"check_conf_keys_declared: OK (корень + {len(services)} сервисных слоёв)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
