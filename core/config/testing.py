"""
Утилита для проверки тестового окружения.

Единая точка проверки TESTING флага вместо разнородных
os.getenv("TESTING") / os.environ.get("TESTING") по всему проекту.
"""

import os


def is_testing() -> bool:
    """
    Проверяет, запущен ли код в тестовом окружении.

    Единый способ проверки вместо разнородных:
    - os.getenv("TESTING") == "true"
    - os.environ.get("TESTING", "").lower() in ("true", "1", "yes")
    - os.getenv("TESTING") != "true"

    Возвращает:
        True если TESTING=true или PYTEST_CURRENT_TEST установлен
    """
    return (
        os.environ.get("TESTING", "").lower() == "true"
        or os.environ.get("PYTEST_CURRENT_TEST") is not None
    )
