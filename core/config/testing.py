"""Единая проверка тестового контура: флаг TESTING и маркер pytest."""

import os


def is_testing() -> bool:
    """True, если процесс запущен с TESTING=true или внутри pytest."""
    return (
        os.environ.get("TESTING", "").lower() == "true"
        or os.environ.get("PYTEST_CURRENT_TEST") is not None
    )
