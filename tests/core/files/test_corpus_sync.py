"""Проверка наличия файлов корпуса example-docs (sync с Unstructured GitHub)."""

from __future__ import annotations

import httpx
import pytest

from tests.core.files.corpus.manifest import (
    ALL_PATHS,
    CORPUS,
    CORPUS_DIR,
    READER_CORPUS_PREFIX_EXCLUDE,
    READER_REMOTE_PATHS,
)

_EVAL_PREFIX = READER_CORPUS_PREFIX_EXCLUDE[0]


def test_corpus_manifest_files_exist_on_disk() -> None:
    missing = [entry.relative_path for entry in CORPUS if not entry.path.exists()]
    assert missing == [], (
        "Отсутствуют файлы корпуса. Запустите: make sync-example-docs\n"
        + "\n".join(missing[:20])
        + (f"\n... ещё {len(missing) - 20}" if len(missing) > 20 else "")
    )


def test_corpus_manifest_covers_all_reader_files() -> None:
    assert ALL_PATHS == READER_REMOTE_PATHS


@pytest.mark.timeout(120)
def test_corpus_local_matches_github_tree() -> None:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    with httpx.Client(headers=headers, timeout=60.0) as client:
        response = client.get(
            "https://api.github.com/repos/Unstructured-IO/unstructured/git/trees/main?recursive=1"
        )
        response.raise_for_status()
        tree = response.json()["tree"]

    remote_reader: dict[str, int] = {}
    remote_eval: dict[str, int] = {}
    for item in tree:
        if item.get("type") != "blob":
            continue
        path_in_repo = str(item["path"])
        if not path_in_repo.startswith("example-docs/"):
            continue
        rel = path_in_repo[len("example-docs/") :]
        size = item.get("size")
        if not isinstance(size, int):
            raise AssertionError(f"GitHub blob missing size: {path_in_repo}")
        if rel.startswith(_EVAL_PREFIX):
            remote_eval[rel] = size
            continue
        remote_reader[rel] = size

    size_mismatches: list[str] = []
    for rel, expected_size in remote_reader.items():
        local_path = CORPUS_DIR / rel
        assert local_path.is_file(), f"Missing reader corpus file: {rel}"
        actual_size = local_path.stat().st_size
        if actual_size != expected_size:
            size_mismatches.append(f"{rel}: local={actual_size}, remote={expected_size}")

    assert size_mismatches == [], "\n".join(size_mismatches[:20])

    for rel, expected_size in remote_eval.items():
        local_path = CORPUS_DIR / rel
        assert local_path.is_file(), f"Missing eval artifact: {rel}"
        assert local_path.stat().st_size == expected_size


@pytest.mark.timeout(120)
def test_example_docs_github_tree_reachable() -> None:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    with httpx.Client(headers=headers, timeout=60.0) as client:
        response = client.get(
            "https://api.github.com/repos/Unstructured-IO/unstructured/git/trees/main?recursive=1"
        )
        response.raise_for_status()
        tree = response.json()["tree"]
    remote_count = sum(
        1 for item in tree if item["type"] == "blob" and item["path"].startswith("example-docs/")
    )
    local_count = sum(
        1
        for path in CORPUS_DIR.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )
    assert remote_count == local_count, (
        f"Локальный корпус ({local_count}) != remote tree ({remote_count}); "
        "запустите make sync-example-docs"
    )
