"""Утилиты."""

import json
import re

from core.types import JsonValue, parse_json_value

from .merge import deep_merge


def extract_json_from_response(text: str) -> JsonValue | None:
    """
    Извлекает JSON из текста.

    Поддерживает:
    - JSON в markdown блоке ```json ... ```
    - Прямой JSON объект или массив

    Возвращает:
        Распарсенный JSON или None если JSON не найден.
    """
    if not text:
        return None

    # Markdown: ```json ... ``` / ``` ... ``` (регистронезависимо json)
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if match:
        try:
            return parse_json_value(match.group(1).strip(), "response.json_block")
        except (ValueError, json.JSONDecodeError):
            pass

    # Пробуем распарсить как JSON напрямую
    stripped = text.strip()
    if stripped.startswith('{') or stripped.startswith('['):
        try:
            return parse_json_value(stripped, "response.json")
        except (ValueError, json.JSONDecodeError):
            pass

    return None


__all__ = ["deep_merge", "extract_json_from_response"]
