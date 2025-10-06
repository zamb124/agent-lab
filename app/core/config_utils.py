"""
Утилиты для работы с конфигурацией.
Поддерживает загрузку из .env и переопределение через conf.json
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

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            logger.info(f"Конфигурация загружена из {config_path}")
            return config
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON в {config_path}: {e}")
        return {}
    except Exception as e:
        logger.error(f"Ошибка чтения файла {config_path}: {e}")
        return {}


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
            # Рекурсивное объединение для вложенных словарей
            result[key] = merge_configs(result[key], value)
        else:
            # Простое переопределение
            result[key] = value

    return result


def get_config_paths() -> list[Path]:
    """
    Возвращает список путей для поиска файлов конфигурации.
    Порядок важен - последние файлы переопределяют предыдущие.

    Returns:
        Список путей к файлам конфигурации
    """
    # Определяем корневую директорию проекта
    current_dir = Path(__file__).parent
    app_dir = current_dir.parent
    project_root = app_dir.parent

    config_paths = [
        # Локальная конфигурация в корне проекта
        project_root / "conf.json",
        # Локальная конфигурация разработчика (не коммитится)
        project_root / "conf.local.json",
    ]

    # Также проверяем переменную окружения для кастомного пути
    custom_config = os.getenv("AGENT_CONFIG_PATH")
    if custom_config:
        config_paths.append(Path(custom_config))

    return config_paths


def load_merged_config() -> Dict[str, Any]:
    """
    Загружает и объединяет все файлы конфигурации.

    Returns:
        Итоговая объединенная конфигурация
    """
    merged_config = {}
    config_paths = get_config_paths()

    for config_path in config_paths:
        config = load_json_config(config_path)
        if config:
            merged_config = merge_configs(merged_config, config)
            logger.debug(f"Применена конфигурация из {config_path}")

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
    # Сначала проверяем переменную окружения
    env_value = os.getenv(env_key)
    if env_value is not None:
        return env_value

    # Затем проверяем конфигурацию
    config_value = get_nested_value(config, config_key)
    if config_value is not None:
        return config_value

    return default


def resolve_config_value(
    field_name: str, field_type: type, json_config: Dict[str, Any], config_path: str
) -> Any:
    """
    Автоматически разрешает значение конфигурации из env или JSON.

    Args:
        field_name: Имя поля
        field_type: Тип поля
        json_config: JSON конфигурация
        config_path: Путь в конфигурации (например "auth.enabled")

    Returns:
        Разрешенное значение
    """
    # Формируем имя переменной окружения
    env_key = config_path.upper().replace(".", "_")

    # Получаем значение
    value = get_env_or_config(env_key, config_path, json_config)

    if value is None:
        return None

    # Преобразуем тип если нужно
    if field_type is bool and isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    elif field_type is int and isinstance(value, str):
        return int(value)
    elif field_type is float and isinstance(value, str):
        return float(value)

    return value
