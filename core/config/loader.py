"""
Утилиты для загрузки конфигурации с каскадным объединением.

Поддерживает: base config.json + service config.json + env переменные
"""

import json
import os
import logging
from typing import Dict, Any, Union
from pathlib import Path

logger = logging.getLogger(__name__)


def load_json_config(config_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Загружает JSON конфигурацию из файла.

    Args:
        config_path: Путь к файлу конфигурации

    Returns:
        Словарь с конфигурацией или пустой словарь если файл не найден
    """
    config_path = Path(config_path)

    if not config_path.exists():
        logger.info(
            f"Файл конфигурации {config_path} не найден, используем значения по умолчанию"
        )
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
        logger.info(f"Конфигурация загружена из {config_path}")
        return config


def merge_configs(
    base_config: Dict[str, Any], override_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Рекурсивно объединяет два словаря конфигурации.
    override_config имеет приоритет над base_config.

    Args:
        base_config: Базовая конфигурация
        override_config: Конфигурация для переопределения

    Returns:
        Объединенная конфигурация
    """
    result = base_config.copy()

    for key, value in override_config.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value

    return result


def get_config_paths() -> list[Path]:
    """
    Возвращает список путей для поиска файлов конфигурации.
    Порядок важен - последние файлы переопределяют предыдущие.

    Returns:
        Список путей к файлам конфигурации
    """
    current_dir = Path(__file__).parent
    core_dir = current_dir.parent
    project_root = core_dir.parent

    config_paths = [
        project_root / "conf.json",
        project_root / "conf.local.json",
    ]

    custom_config = os.getenv("AGENT_CONFIG_PATH")
    if custom_config:
        config_paths.append(Path(custom_config))

    return config_paths


def remove_env_overridden_values(config: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """
    Удаляет из конфигурации значения, которые переопределены через env переменные.
    Это нужно чтобы env переменные имели приоритет над JSON конфигурацией.
    
    Args:
        config: Словарь конфигурации
        prefix: Префикс для построения имени env переменной
    
    Returns:
        Конфигурация без значений переопределенных через env
    """
    result = {}
    
    for key, value in config.items():
        env_key = f"{prefix}__{key}".upper() if prefix else key.upper()
        
        if os.getenv(env_key) is not None:
            logger.debug(f"Пропускаем {key} из JSON, используется env переменная {env_key}")
            continue
        
        if isinstance(value, dict):
            nested_result = remove_env_overridden_values(value, env_key)
            if nested_result:
                result[key] = nested_result
        else:
            result[key] = value
    
    return result


def load_merged_config(
    base_config_path: Path = None,
    service_config_path: Path = None
) -> Dict[str, Any]:
    """
    Загружает и объединяет конфигурации:
    1. Базовый config.json
    2. Service config.json (если есть)
    3. Удаляет значения переопределенные через env

    Args:
        base_config_path: Путь к базовой конфигурации
        service_config_path: Путь к конфигурации сервиса

    Returns:
        Итоговая объединенная конфигурация
    """
    merged_config = {}

    if base_config_path is None:
        config_paths = get_config_paths()
        for config_path in config_paths:
            config = load_json_config(config_path)
            if config:
                merged_config = merge_configs(merged_config, config)
                logger.debug(f"Применена конфигурация из {config_path}")
    else:
        base_config = load_json_config(base_config_path)
        if base_config:
            merged_config = base_config

    if service_config_path:
        service_config = load_json_config(service_config_path)
        if service_config:
            merged_config = merge_configs(merged_config, service_config)
            logger.info(f"Применена service конфигурация из {service_config_path}")

    merged_config = remove_env_overridden_values(merged_config)
    
    return merged_config


def get_nested_value(config: Dict[str, Any], key_path: str, default: Any = None) -> Any:
    """
    Получает значение по вложенному ключу (например, "auth.providers.yandex.client_id").

    Args:
        config: Словарь конфигурации
        key_path: Путь к ключу через точку
        default: Значение по умолчанию

    Returns:
        Значение или default
    """
    keys = key_path.split(".")
    current = config

    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default

    return current


def set_nested_value(config: Dict[str, Any], key_path: str, value: Any) -> None:
    """
    Устанавливает значение по вложенному ключу.

    Args:
        config: Словарь конфигурации
        key_path: Путь к ключу через точку
        value: Значение для установки
    """
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
    """
    Получает значение из переменной окружения или конфигурации.
    Переменная окружения имеет приоритет.

    Args:
        env_key: Ключ переменной окружения
        config_key: Ключ в конфигурации (может быть вложенным)
        config: Словарь конфигурации
        default: Значение по умолчанию

    Returns:
        Значение из env, config или default
    """
    env_value = os.getenv(env_key)
    if env_value is not None:
        return env_value

    config_value = get_nested_value(config, config_key)
    if config_value is not None:
        return config_value

    return default

