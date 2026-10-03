"""Единственный cast результата page.evaluate: stub Playwright отдаёт Any."""

from __future__ import annotations

from typing import cast

from apps.browser.models.types import BrowserPage
from core.types import JsonValue, require_json_value


async def evaluate_json_value(page: BrowserPage, source: str, field_name: str) -> JsonValue:
    return require_json_value(cast(object, await page.evaluate(source)), field_name)
