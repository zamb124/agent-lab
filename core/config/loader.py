"""
Утилиты для загрузки конфигурации с каскадным объединением.

Корень проекта: conf.json + conf.local.json. Переопределения сервисов — в conf.json
в ключе services.<имя_сервиса> (без отдельных conf.json в apps/).
"""

import os
from pathlib import Path

from core.logging import get_logger
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

logger = get_logger(__name__)
_PROJECT_ROOT_ENV = "AGENT_LAB_PROJECT_ROOT"

def get_project_root() -> Path:
    """
    Корень монорепозитория (pyproject.toml, core/, apps/).

    Не использовать Path(__file__).parent... от factory: при установке в .venv путь ведёт в
    site-packages, а documentation-dist и conf.json лежат в корне репозитория.
    """
    env = os.environ.get(_PROJECT_ROOT_ENV)
    if env:
        p = Path(env).expanduser().resolve()
        if not p.is_dir():
            raise ValueError(f"{_PROJECT_ROOT_ENV} не каталог: {p}")
        return p

    start = Path(__file__).resolve()
    for d in start.parents:
        if (
            (d / "pyproject.toml").is_file()
            and (d / "core").is_dir()
            and (d / "apps").is_dir()
        ):
            return d

    raise RuntimeError(
        f"Корень репозитория agent-lab не найден (ожидаются pyproject.toml, core/, apps/ вверх по пути от {start}). Задайте {_PROJECT_ROOT_ENV} или запускайте из дерева исходников (uv sync из корня репозитория)."
    )

def load_json_config(config_path: str | Path, *, silent: bool = False) -> JsonObject:
    config_path = Path(config_path)

    if not config_path.exists():
        if not silent:
            logger.info(
                "config.loader.file_missing_default",
                path=str(config_path),
            )
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        config = parse_json_object(f.read(), str(config_path))
        if not silent:
            logger.info(
                "config.loader.file_loaded",
                path=str(config_path),
            )
        return config

def merge_configs(
    base_config: JsonObject, override_config: JsonObject
) -> JsonObject:
    result = base_config.copy()

    for key, value in override_config.items():
        base_value = result.get(key)
        if isinstance(base_value, dict) and isinstance(value, dict):
            result[key] = merge_configs(
                require_json_object(base_value, f"config.{key}"),
                require_json_object(value, f"config.{key}"),
            )
        else:
            result[key] = value

    return result

def get_config_paths() -> list[Path]:
    project_root = get_project_root()

    config_paths = [
        project_root / "conf.json",
        project_root / "conf.local.json",
    ]

    custom_config = os.getenv("AGENT_CONFIG_PATH")
    if custom_config:
        config_paths.append(Path(custom_config))

    return config_paths

def remove_env_overridden_values(
    config: JsonObject,
    prefix: str = "",
    *,
    silent: bool = False,
) -> JsonObject:
    result: JsonObject = {}

    for key, value in config.items():
        env_key = f"{prefix}__{key}".upper() if prefix else key.upper()

        if os.getenv(env_key):
            if not silent:
                logger.debug(
                    "config.loader.env_override_skip",
                    key=key,
                    env_key=env_key,
                )
            continue

        if isinstance(value, dict):
            nested_result = remove_env_overridden_values(value, env_key, silent=silent)
            if nested_result:
                result[key] = nested_result
        else:
            result[key] = value

    return result

def load_merged_config(
    service_name: str | None = None,
    *,
    silent: bool = False,
) -> JsonObject:
    """
    Загружает конфигурацию: conf.json + conf.local.json (+ AGENT_CONFIG_PATH),
    затем при service_name — сливает services.<service_name> поверх общего слоя.

    Ключ services не передаётся в Pydantic (удаляется из результата).

    silent=True — без записей в лог (до setup_logging в HTTP и воркерах).
    """
    merged: JsonObject = {}

    for config_path in get_config_paths():
        config = load_json_config(config_path, silent=silent)
        if config:
            merged = merge_configs(merged, config)
            if not silent:
                logger.debug(
                    "config.loader.layer_merged",
                    path=str(config_path),
                )

    if service_name:
        services_value = merged.get("services")
        service_overrides_value = (
            services_value.get(service_name) if isinstance(services_value, dict) else None
        )
        if service_overrides_value is not None:
            overrides = require_json_object(
                service_overrides_value,
                f"services.{service_name}",
            )
            merged = merge_configs(merged, overrides)
            if not silent:
                logger.info(
                    "config.loader.service_layer_merged",
                    service_name=service_name,
                )

    _ = merged.pop("services", None)
    merged = remove_env_overridden_values(merged, silent=silent)

    return merged

def get_nested_value(
    config: JsonObject, key_path: str, default: JsonValue | None = None
) -> JsonValue | None:
    keys = key_path.split(".")
    current: JsonValue = config

    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default

    return current

def set_nested_value(config: JsonObject, key_path: str, value: JsonValue) -> None:
    keys = key_path.split(".")
    current = config

    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        next_value = current[key]
        if not isinstance(next_value, dict):
            raise ValueError(f"config path {key_path!r} crosses non-object key {key!r}")
        current = require_json_object(next_value, f"config.{key}")

    current[keys[-1]] = value

def get_env_or_config(
    env_key: str, config_key: str, config: JsonObject, default: JsonValue | None = None
) -> JsonValue | None:
    env_value = os.getenv(env_key)
    if env_value is not None:
        return env_value

    config_value = get_nested_value(config, config_key)
    if config_value is not None:
        return config_value

    return default
