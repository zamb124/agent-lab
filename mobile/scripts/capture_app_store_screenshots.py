"""
Скриншоты для витрины App Store (iPhone 6.7": 1290×2796), формат имён для fastlane.

Запуск из корня репозитория:
  uv run playwright install chromium   # один раз
  export STORE_SCREENSHOT_BASE_URL=https://humanitec.ru
  uv run python mobile/scripts/capture_app_store_screenshots.py

Публичные URL без логина; для экранов из личного кабинета позже добавьте cookie (см. tests/ui).
"""

from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_BASE = ROOT / "mobile" / "store-listing" / "metadata"

WIDTH = 1290
HEIGHT = 2796
DEVICE_FILENAME_PREFIX = "iPhone 15 Pro Max"

SCREENSHOT_JOBS: list[tuple[str, int]] = [
    ("/", 0),
    ("/terms", 1),
]


def main() -> None:
    base = os.environ.get("STORE_SCREENSHOT_BASE_URL", "https://humanitec.ru").rstrip("/")
    locale = os.environ.get("STORE_SCREENSHOT_LOCALE", "ru")
    headed = os.environ.get("STORE_SCREENSHOT_HEADED", "").strip() == "1"

    out_dir = OUTPUT_BASE / locale / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        context = browser.new_context(
            viewport={"width": WIDTH, "height": HEIGHT},
            device_scale_factor=1,
        )
        page = context.new_page()
        for path, idx in SCREENSHOT_JOBS:
            url = f"{base}{path}" if path.startswith("/") else f"{base}/{path}"
            page.goto(url, wait_until="networkidle", timeout=120_000)
            name = f"{DEVICE_FILENAME_PREFIX}-{idx}.png"
            page.screenshot(path=str(out_dir / name), full_page=False)
        browser.close()

    print(f"OK: {out_dir}")


if __name__ == "__main__":
    main()
