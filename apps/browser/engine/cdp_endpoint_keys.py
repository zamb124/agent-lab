"""
Каноничные ключи CDP endpoint-ов для Browser Runtime.

Инвариант задачи:
- Всё, что включено для Lightpanda по `endpoint_key`, должно 1:1 включаться для Chromium,
  без отдельных конфигов и без отдельных профилей.
"""

from __future__ import annotations

LIGHTPANDA_COMPAT_ENDPOINT_KEYS: set[str] = {
    "lightpanda",
    "chromium",
}


def is_lightpanda_compat_endpoint(endpoint_key: str) -> bool:
    if not endpoint_key:
        raise ValueError("endpoint_key обязателен")
    return endpoint_key in LIGHTPANDA_COMPAT_ENDPOINT_KEYS

