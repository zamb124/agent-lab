"""Скачивает example-docs из Unstructured-IO/unstructured в tests/core/files/example-docs/.

Использует GitHub Contents API (без токена, публичный репозиторий).
Идемпотентен: пропускает уже скачанные файлы с совпадающим размером.

Тяжёлые файлы (>SIZE_LIMIT_BYTES) сохраняются в tests/.cache/example-docs-large/
и не входят в git-коммит (покрыты .gitignore).

Запуск:
    uv run python scripts/download_example_docs.py
    uv run python scripts/download_example_docs.py --force    # пере-скачать всё
    uv run python scripts/download_example_docs.py --large    # скачать и тяжёлые
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

REPO = "Unstructured-IO/unstructured"
BRANCH = "main"
EXAMPLE_DOCS_PREFIX = "example-docs/"
BASE_API = "https://api.github.com"
RAW_BASE = "https://raw.githubusercontent.com"

SIZE_LIMIT_BYTES = 5 * 1024 * 1024  # 5 MB — граница «тяжёлых» файлов

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "tests" / "core" / "files" / "example-docs"
LARGE_CACHE_DIR = REPO_ROOT / "tests" / ".cache" / "example-docs-large"


def _get_tree(client: httpx.Client) -> list[dict]:
    """Возвращает плоский список всех blob-записей example-docs из git tree."""
    url = f"{BASE_API}/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
    resp = client.get(url)
    resp.raise_for_status()
    data = resp.json()
    return [
        item
        for item in data.get("tree", [])
        if item["type"] == "blob" and item["path"].startswith(EXAMPLE_DOCS_PREFIX)
    ]


def _download_blob(client: httpx.Client, path_in_repo: str) -> bytes:
    url = f"{RAW_BASE}/{REPO}/{BRANCH}/{path_in_repo}"
    for attempt in range(3):
        try:
            resp = client.get(url, timeout=120.0)
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPStatusError:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Пере-скачать существующие файлы")
    parser.add_argument("--large", action="store_true", help="Скачать тяжёлые файлы (>5MB) в .cache/")
    args = parser.parse_args(argv)

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    LARGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    with httpx.Client(headers=headers, follow_redirects=True) as client:
        print("Получаю список файлов из GitHub API...")
        tree = _get_tree(client)
        print(f"Найдено {len(tree)} файлов в example-docs/")

        downloaded = skipped = large_skipped = 0
        for item in tree:
            rel = item["path"][len(EXAMPLE_DOCS_PREFIX):]  # путь внутри example-docs/
            size = item.get("size", 0)
            is_large = size > SIZE_LIMIT_BYTES

            if is_large:
                if not args.large:
                    print(f"  [large, skip] {rel}  ({size / 1024 / 1024:.1f} MB)")
                    large_skipped += 1
                    continue
                dest = LARGE_CACHE_DIR / rel
            else:
                dest = CORPUS_DIR / rel

            dest.parent.mkdir(parents=True, exist_ok=True)

            if dest.exists() and not args.force and dest.stat().st_size == size:
                skipped += 1
                continue

            print(f"  [{size:>9} B] {rel}")
            data = _download_blob(client, item["path"])
            dest.write_bytes(data)
            downloaded += 1

            # небольшая пауза чтобы не дергать API слишком быстро
            time.sleep(0.05)

    print(f"\nГотово: скачано {downloaded}, пропущено {skipped}, тяжёлых пропущено {large_skipped}.")
    print(f"Корпус: {CORPUS_DIR}")
    if large_skipped:
        print(f"Тяжёлые файлы доступны через --large: {LARGE_CACHE_DIR}")


if __name__ == "__main__":
    main(sys.argv[1:])
