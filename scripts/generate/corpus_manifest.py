#!/usr/bin/env python3
"""Генерирует tests/core/files/corpus/manifest_generated.py из GitHub tree + overrides.yaml.

Запуск:
    uv run python -m scripts.generate.corpus_manifest
    uv run python -m scripts.generate.corpus_manifest --check
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

import httpx2
import yaml

from core.files.reader import FileReader
from core.files.reader.models import FileReadKind

REPO = "Unstructured-IO/unstructured"
BRANCH = "main"
EXAMPLE_DOCS_PREFIX = "example-docs/"
READER_CORPUS_PREFIX_EXCLUDE = ("test_evaluate_files/",)

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = REPO_ROOT / "tests" / "core" / "files" / "example-docs"
OVERRIDES_PATH = REPO_ROOT / "tests" / "core" / "files" / "corpus" / "overrides.yaml"
GENERATED_PATH = REPO_ROOT / "tests" / "core" / "files" / "corpus" / "manifest_generated.py"

DEFAULT_UNSUPPORTED_PATHS = frozenset(
    {
        "password_protected.xlsx",
        "empty.xlsx",
        "eml/empty.eml",
        "simple.zip",
        "file_we_dont_want_imported",
        "fake-power-point.ppt",
        "pdf/pdf-bad-color-space.pdf",
    }
)

DEFAULT_ALLOWS_EMPTY_TEXT = frozenset(
    {
        "empty.txt",
        "fake-text-all-whitespace.txt",
        "pdf/password.pdf",
        "pdf/copy-protected.pdf",
        "picture.pptx",
        "test-image-jpg-mime.pptx",
        "pdf/single_table.pdf",
        "fake-encrypted.msg",
        "eml/fake-encrypted.eml",
    }
)

DEFAULT_VISION_SUBSTRING = "MOCK_VISION"


class OverrideEntry(TypedDict, total=False):
    expected_kind: str
    expected_text_substring: str | None
    expected_min_pages: int
    is_unsupported: bool
    uses_vision_llm: bool
    uses_mock_stt_tier: bool
    allows_empty_text: bool
    skip_reason: str | None


class GitHubTreeBlob(TypedDict):
    path: str
    type: str


class GitHubTreeResponse(TypedDict):
    tree: list[GitHubTreeBlob]


@dataclass(frozen=True)
class GeneratedCorpusFile:
    relative_path: str
    expected_kind: FileReadKind
    expected_text_substring: str | None = None
    expected_min_pages: int = 1
    is_unsupported: bool = False
    uses_vision_llm: bool = False
    uses_mock_stt_tier: bool = False
    allows_empty_text: bool = False
    skip_reason: str | None = None


def _fetch_reader_paths() -> list[str]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    with httpx2.Client(headers=headers, timeout=60.0) as client:
        response = client.get(
            f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
        )
        _ = response.raise_for_status()
        tree_raw = cast(GitHubTreeResponse, response.json())["tree"]
    paths: list[str] = []
    for item in tree_raw:
        if item["type"] != "blob":
            continue
        path_in_repo = item["path"]
        if not path_in_repo.startswith(EXAMPLE_DOCS_PREFIX):
            continue
        rel = path_in_repo[len(EXAMPLE_DOCS_PREFIX) :]
        if rel.startswith(READER_CORPUS_PREFIX_EXCLUDE):
            continue
        paths.append(rel)
    paths.sort()
    return paths


def _load_overrides() -> dict[str, OverrideEntry]:
    if not OVERRIDES_PATH.exists():
        return {}
    loaded = cast(object, yaml.safe_load(OVERRIDES_PATH.read_text(encoding="utf-8")))
    if not isinstance(loaded, dict):
        raise RuntimeError(f"{OVERRIDES_PATH}: expected mapping root")
    raw_mapping = cast(dict[str, object], loaded)
    entries_object = raw_mapping.get("entries")
    if not isinstance(entries_object, dict):
        raise RuntimeError(f"{OVERRIDES_PATH}: expected entries mapping")
    entries_mapping = cast(dict[str, object], entries_object)
    overrides: dict[str, OverrideEntry] = {}
    for rel_path, entry_object in entries_mapping.items():
        if not isinstance(entry_object, dict):
            raise RuntimeError(f"{OVERRIDES_PATH}: entry {rel_path} must be mapping")
        overrides[rel_path] = cast(OverrideEntry, cast(object, entry_object))
    return overrides


def _infer_kind(rel_path: str, reader: FileReader) -> FileReadKind:
    path = CORPUS_DIR / rel_path
    if not path.is_file():
        raise FileNotFoundError(f"Corpus file missing on disk: {rel_path}")
    head = path.read_bytes()[:8192]
    info = reader.recognize_file_type(file_name=path.name, head=head)
    return info.detected_kind


def _build_entry(rel_path: str, overrides: dict[str, OverrideEntry], reader: FileReader) -> GeneratedCorpusFile:
    override = overrides.get(rel_path, {})
    inferred_kind = _infer_kind(rel_path, reader)
    kind_raw = str(override.get("expected_kind", inferred_kind.value)).lower()
    expected_kind = FileReadKind(kind_raw)

    uses_vision_llm = bool(override.get("uses_vision_llm", rel_path.startswith("img/")))
    uses_mock_stt_tier = bool(
        override.get("uses_mock_stt_tier", expected_kind == FileReadKind.AUDIO)
    )
    is_unsupported = bool(
        override.get("is_unsupported", rel_path in DEFAULT_UNSUPPORTED_PATHS)
    )
    allows_empty_text = bool(
        override.get("allows_empty_text", rel_path in DEFAULT_ALLOWS_EMPTY_TEXT)
    )

    expected_text_substring: str | None
    if "expected_text_substring" in override:
        expected_text_substring = override["expected_text_substring"]
    elif uses_vision_llm:
        expected_text_substring = DEFAULT_VISION_SUBSTRING
    else:
        expected_text_substring = None

    expected_min_pages = int(override.get("expected_min_pages", 1))
    skip_reason = override.get("skip_reason")
    if skip_reason is not None:
        skip_reason = str(skip_reason)

    return GeneratedCorpusFile(
        relative_path=rel_path,
        expected_kind=expected_kind,
        expected_text_substring=expected_text_substring,
        expected_min_pages=expected_min_pages,
        is_unsupported=is_unsupported,
        uses_vision_llm=uses_vision_llm,
        uses_mock_stt_tier=uses_mock_stt_tier,
        allows_empty_text=allows_empty_text,
        skip_reason=skip_reason,
    )


def _format_corpus_file(entry: GeneratedCorpusFile) -> str:
    positional: list[str] = [
        f'"{entry.relative_path}"',
        f"FileReadKind.{entry.expected_kind.name}",
    ]
    if entry.expected_text_substring is not None:
        positional.append(repr(entry.expected_text_substring))

    kwargs: list[str] = []
    if entry.expected_min_pages != 1:
        kwargs.append(f"expected_min_pages={entry.expected_min_pages}")
    if entry.is_unsupported:
        kwargs.append("is_unsupported=True")
    if entry.uses_vision_llm:
        kwargs.append("uses_vision_llm=True")
    if entry.uses_mock_stt_tier:
        kwargs.append("uses_mock_stt_tier=True")
    if entry.allows_empty_text:
        kwargs.append("allows_empty_text=True")
    if entry.skip_reason is not None:
        kwargs.append(f"skip_reason={entry.skip_reason!r}")

    return f"CorpusFile({', '.join(positional + kwargs)})"


def _render_generated(entries: tuple[GeneratedCorpusFile, ...], reader_paths: list[str]) -> str:
    lines = [
        '"""AUTO-GENERATED by scripts/generate/corpus_manifest.py — не редактировать вручную."""',
        "",
        "from __future__ import annotations",
        "",
        "from core.files.reader.models import FileReadKind",
        "from tests.core.files.corpus.models import CorpusFile",
        "",
        "CORPUS: tuple[CorpusFile, ...] = (",
    ]
    for entry in entries:
        lines.append(f"    {_format_corpus_file(entry)},")
    lines.append(")")
    lines.append("")
    lines.append("READER_REMOTE_PATHS: frozenset[str] = frozenset(")
    lines.append(repr(reader_paths))
    lines.append(")")
    lines.append("")
    return "\n".join(lines)


def generate() -> str:
    reader_paths = _fetch_reader_paths()
    overrides = _load_overrides()
    reader = FileReader()
    entries = tuple(
        _build_entry(rel_path, overrides, reader) for rel_path in reader_paths
    )
    return _render_generated(entries, reader_paths)


def main(argv: list[str] | None = None) -> int:
    check_mode = bool(argv and "--check" in argv)

    rendered = generate()
    if check_mode:
        if not GENERATED_PATH.exists():
            print(f"{GENERATED_PATH} missing; run generate_corpus_manifest.py", file=sys.stderr)
            return 1
        if GENERATED_PATH.read_text(encoding="utf-8") != rendered:
            print(f"{GENERATED_PATH} is stale; run generate_corpus_manifest.py", file=sys.stderr)
            return 1
        print("manifest_generated.py: OK")
        return 0

    _ = GENERATED_PATH.write_text(rendered, encoding="utf-8")
    print(f"Wrote {GENERATED_PATH} ({rendered.count('CorpusFile(')} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
