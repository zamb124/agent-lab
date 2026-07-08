"""Скачивает example-docs из Unstructured-IO/unstructured в tests/core/files/example-docs/.

Использует GitHub Git Trees API (без токена, публичный репозиторий).
Идемпотентен: пропускает уже скачанные файлы с совпадающим размером.

Все blobs (включая >5 MB для Git LFS) сохраняются в tests/core/files/example-docs/.

Запуск:
    uv run python scripts/download_example_docs.py
    uv run python scripts/download_example_docs.py --force
    make sync-example-docs
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import TypedDict, cast

import httpx

REPO = "Unstructured-IO/unstructured"
BRANCH = "main"
EXAMPLE_DOCS_PREFIX = "example-docs/"
BASE_API = "https://api.github.com"
RAW_BASE = "https://raw.githubusercontent.com"

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "tests" / "core" / "files" / "example-docs"


class GitHubTreeBlob(TypedDict):
    path: str
    type: str
    size: int


class GitHubTreeResponse(TypedDict):
    tree: list[GitHubTreeBlob]


def _get_tree(client: httpx.Client) -> list[GitHubTreeBlob]:
    """Возвращает плоский список всех blob-записей example-docs из git tree."""
    url = f"{BASE_API}/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
    resp = client.get(url)
    _ = resp.raise_for_status()
    data = cast(GitHubTreeResponse, resp.json())
    return [
        item
        for item in data["tree"]
        if item["type"] == "blob" and item["path"].startswith(EXAMPLE_DOCS_PREFIX)
    ]


def _download_blob(client: httpx.Client, path_in_repo: str) -> bytes:
    url = f"{RAW_BASE}/{REPO}/{BRANCH}/{path_in_repo}"
    for attempt in range(3):
        try:
            resp = client.get(url, timeout=300.0)
            _ = resp.raise_for_status()
            return resp.content
        except httpx.HTTPStatusError:
            if attempt == 2:
                raise
            backoff_seconds = 1.0 if attempt == 0 else 2.0
            time.sleep(backoff_seconds)
    raise RuntimeError("unreachable")


def _parse_force(argv: list[str] | None) -> bool:
    return bool(argv and "--force" in argv)


def main(argv: list[str] | None = None) -> int:
    force = _parse_force(argv)

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)

    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    missing: list[str] = []
    with httpx.Client(headers=headers, follow_redirects=True) as client:
        print("Получаю список файлов из GitHub API...")
        tree = _get_tree(client)
        print(f"Найдено {len(tree)} файлов в example-docs/")

        downloaded = skipped = 0
        for item in tree:
            path_in_repo = item["path"]
            rel = path_in_repo[len(EXAMPLE_DOCS_PREFIX) :]
            size = item["size"]
            dest = CORPUS_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)

            if dest.exists() and not force and dest.stat().st_size == size:
                skipped += 1
                continue

            size_mb = size / 1024 / 1024
            label = f"{size_mb:.1f} MB" if size_mb >= 1 else f"{size} B"
            print(f"  [{label:>10}] {rel}")
            data = _download_blob(client, path_in_repo)
            if len(data) != size:
                raise RuntimeError(
                    f"Размер {rel} не совпал: GitHub={size}, downloaded={len(data)}"
                )
            _ = dest.write_bytes(data)
            downloaded += 1
            time.sleep(0.05)

        for item in tree:
            rel = item["path"][len(EXAMPLE_DOCS_PREFIX) :]
            dest = CORPUS_DIR / rel
            expected = item["size"]
            if not dest.exists():
                missing.append(rel)
                continue
            actual = dest.stat().st_size
            if actual != expected:
                missing.append(f"{rel} (size {actual} != {expected})")

    print(f"\nГотово: скачано {downloaded}, пропущено {skipped}.")
    print(f"Корпус: {CORPUS_DIR}")
    if missing:
        print("Отсутствуют или размер не совпал:", file=sys.stderr)
        for path in missing[:20]:
            print(f"  - {path}", file=sys.stderr)
        if len(missing) > 20:
            print(f"  ... ещё {len(missing) - 20}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
