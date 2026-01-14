"""Утилиты."""

import json
import re
from typing import Any

from .merge import deep_merge


def extract_json_from_response(text: str) -> Any:
    """
    Извлекает JSON из текста.
    
    Поддерживает:
    - JSON в markdown блоке ```json ... ```
    - Прямой JSON объект или массив
    
    Returns:
        Распарсенный JSON или None если JSON не найден.
    """
    if not text:
        return None
    
    # Пробуем извлечь из markdown блока ```json ... ```
    match = re.search(r'```json\s*([\s\S]*?)```', text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    
    # Пробуем распарсить как JSON напрямую
    stripped = text.strip()
    if stripped.startswith('{') or stripped.startswith('['):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    
    return None


__all__ = ["deep_merge", "extract_json_from_response"]

