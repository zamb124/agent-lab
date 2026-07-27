#!/usr/bin/env python3
"""CI gate: manifest example-docs покрывает все reader-файлы Unstructured GitHub tree."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TypedDict, cast

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Импорт после правки sys.path: корпус тестов лежит вне пакета scripts.
from tests.core.files.corpus.manifest import ALL_PATHS, CORPUS, CORPUS_DIR  # noqa: E402
from tests.core.files.corpus.models import READER_CORPUS_PREFIX_EXCLUDE  # noqa: E402

REPO = "Unstructured-IO/unstructured"
BRANCH = "main"
EXAMPLE_DOCS_PREFIX = "example-docs/"
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".heic", ".webp", ".gif"})
VISION_EXTENSIONS = IMAGE_EXTENSIONS | frozenset({".pdf"})


class GitHubTreeBlob(TypedDict):
    path: str
    type: str


class GitHubTreeResponse(TypedDict):
    tree: list[GitHubTreeBlob]


def _fetch_reader_paths() -> frozenset[str]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    with httpx.Client(headers=headers, timeout=60.0) as client:
        response = client.get(
            f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
        )
        _ = response.raise_for_status()
        tree = cast(GitHubTreeResponse, response.json())["tree"]
    paths: set[str] = set()
    for item in tree:
        if item["type"] != "blob":
            continue
        path_in_repo = item["path"]
        if not path_in_repo.startswith(EXAMPLE_DOCS_PREFIX):
            continue
        rel = path_in_repo[len(EXAMPLE_DOCS_PREFIX) :]
        if rel.startswith(READER_CORPUS_PREFIX_EXCLUDE):
            continue
        paths.add(rel)
    return frozenset(paths)


def main() -> int:
    violations: list[str] = []

    remote_paths = _fetch_reader_paths()
    if ALL_PATHS != remote_paths:
        missing = sorted(remote_paths - ALL_PATHS)
        extra = sorted(ALL_PATHS - remote_paths)
        if missing:
            violations.append(f"manifest missing {len(missing)} reader paths (first: {missing[:5]})")
        if extra:
            violations.append(f"manifest has {len(extra)} stale paths (first: {extra[:5]})")

    missing_on_disk = [entry.relative_path for entry in CORPUS if not entry.path.is_file()]
    if missing_on_disk:
        violations.append(
            f"{len(missing_on_disk)} manifest files missing on disk; run make sync-example-docs"
        )

    for entry in CORPUS:
        if not entry.uses_vision_llm:
            continue
        ext = Path(entry.relative_path).suffix.lower()
        if ext not in VISION_EXTENSIONS:
            violations.append(
                f"uses_vision_llm without image extension: {entry.relative_path} ({ext})"
            )

    generated_check = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_corpus_manifest.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if generated_check.returncode != 0:
        detail = generated_check.stderr.strip() or generated_check.stdout.strip()
        violations.append(detail or "manifest_generated.py stale")

    if violations:
        print("Corpus manifest violations:", file=sys.stderr)
        for item in violations:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print(f"Corpus manifest: OK ({len(CORPUS)} reader entries, corpus dir {CORPUS_DIR})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
