"""AST-нарезка исходника через tree-sitter-language-pack (Parser.parse(str))."""

from __future__ import annotations

from pathlib import Path

import tiktoken
from tree_sitter_language_pack import Node, Parser, Tree, get_parser

from core.rag_indexing_schema import IndexProfileSplitConfig

_ENCODING_NAME = "cl100k_base"

_CODE_LANGUAGE_BY_SUFFIX: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".kt": "kotlin",
    ".swift": "swift",
    ".scala": "scala",
    ".lua": "lua",
    ".r": "r",
    ".sql": "sql",
    ".sh": "bash",
    ".bash": "bash",
}


def resolve_code_language(split_config: IndexProfileSplitConfig, file_name: str) -> str:
    configured = split_config.chonkie_code_language.strip()
    if configured != "auto":
        if not configured:
            raise ValueError("split.strategy=code: chonkie_code_language пустой")
        return configured
    suffix = Path(file_name).suffix.lower()
    if suffix not in _CODE_LANGUAGE_BY_SUFFIX:
        raise ValueError(
            "split.strategy=code: chonkie_code_language=auto требует известный суффикс файла, "
            + f"получен {suffix!r} ({file_name})"
        )
    return _CODE_LANGUAGE_BY_SUFFIX[suffix]


def split_code_text(
    text: str,
    split_config: IndexProfileSplitConfig,
    *,
    file_name: str,
) -> list[str]:
    raw = text.strip()
    if not raw:
        return []
    language = resolve_code_language(split_config, file_name)
    try:
        parser: Parser = get_parser(language)
    except RuntimeError as exc:
        raise ValueError(
            f"split.strategy=code: tree-sitter язык {language!r} недоступен"
        ) from exc
    tree: Tree | None = parser.parse(raw)
    if tree is None:
        raise ValueError(f"split.strategy=code: tree-sitter не разобрал {language!r}")
    root: Node = tree.root_node()
    source_bytes = raw.encode("utf-8")
    named_count = root.named_child_count()
    if named_count == 0:
        return [raw]
    tokenizer = tiktoken.get_encoding(_ENCODING_NAME)
    units: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for index in range(named_count):
        node = root.named_child(index)
        if node is None:
            raise ValueError(
                f"split.strategy=code: named_child({index}) пустой для {language!r}"
            )
        fragment = source_bytes[node.start_byte() : node.end_byte()].decode("utf-8")
        stripped = fragment.strip()
        if not stripped:
            continue
        tokens = len(tokenizer.encode(stripped))
        if current and current_tokens + tokens > split_config.chunk_size:
            units.append("\n\n".join(current))
            current = []
            current_tokens = 0
        current.append(stripped)
        current_tokens += tokens
    if current:
        units.append("\n\n".join(current))
    return units
