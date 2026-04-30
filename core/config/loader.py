"""
Утилиты для загрузки конфигурации с каскадным объединением.

Корень проекта: conf.json + conf.local.json. Переопределения сервисов — в conf.json
в ключе services.<имя_сервиса> (без отдельных conf.json в apps/).
"""

import json

from core.logging import get_logger
import os
from pathlib import Path
from typing import Any, Dict, Union

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
        f"Корень репозитория agent-lab не найден (ожидаются pyproject.toml, core/, apps/ вверх по пути от {start}). "
        f"Задайте {_PROJECT_ROOT_ENV} или запускайте из дерева исходников (uv sync из корня репозитория)."
    )

def load_json_config(config_path: Union[str, Path], *, silent: bool = False) -> Dict[str, Any]:
    config_path = Path(config_path)

    if not config_path.exists():
        if not silent:
            logger.info(
                "config.loader.file_missing_default",
                path=str(config_path),
            )
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
        if not silent:
            logger.info(
                "config.loader.file_loaded",
                path=str(config_path),
            )
        return config

def merge_configs(
    base_config: Dict[str, Any], override_config: Dict[str, Any]
) -> Dict[str, Any]:
    result = base_config.copy()

    for key, value in override_config.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
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
    config: Dict[str, Any],
    prefix: str = "",
    *,
    silent: bool = False,
) -> Dict[str, Any]:
    result = {}

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
) -> Dict[str, Any]:
    """
    Загружает конфигурацию: conf.json + conf.local.json (+ AGENT_CONFIG_PATH),
    затем при service_name — сливает services.<service_name> поверх общего слоя.

    Ключ services не передаётся в Pydantic (удаляется из результата).

    silent=True — без записей в лог (до setup_logging в HTTP и воркерах).
    """
    merged: Dict[str, Any] = {}

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
        overrides = merged.get("services", {}).get(service_name, {})
        if overrides:
            merged = merge_configs(merged, overrides)
            if not silent:
                logger.info(
                    "config.loader.service_layer_merged",
                    service_name=service_name,
                )

    merged.pop("services", None)
    merged = remove_env_overridden_values(merged, silent=silent)

    return merged

def get_nested_value(config: Dict[str, Any], key_path: str, default: Any = None) -> Any:
    keys = key_path.split(".")
    current = config

    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default

    return current

def set_nested_value(config: Dict[str, Any], key_path: str, value: Any) -> None:
    keys = key_path.split(".")
    current = config

    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]

    current[keys[-1]] = value

def get_env_or_config(
    env_key: str, config_key: str, config: Dict[str, Any], default: Any = None
) -> Any:
    env_value = os.getenv(env_key)
    if env_value is not None:
        return env_value

    config_value = get_nested_value(config, config_key)
    if config_value is not None:
        return config_value

    return default
