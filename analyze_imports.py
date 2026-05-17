import ast
import os
from collections import Counter
from collections.abc import Iterable
from typing import Any

LocalImport = dict[str, Any]


def _imported_module(node: ast.Import | ast.ImportFrom) -> str:
    if isinstance(node, ast.ImportFrom):
        return node.module or ""
    return node.names[0].name


def find_local_imports(directory: str) -> list[LocalImport]:
    local_imports: list[LocalImport] = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                with open(filepath, encoding="utf-8") as f:
                    content = f.read()
                tree = ast.parse(content, filename=filepath)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        for child in ast.walk(node):
                            if isinstance(child, (ast.Import, ast.ImportFrom)):
                                local_imports.append(
                                    {
                                        "file": filepath,
                                        "line": child.lineno,
                                        "module": _imported_module(child),
                                    }
                                )
    return local_imports


def _print_counter(title: str, rows: Iterable[tuple[str, int]]) -> None:
    print(f"\n{title}")
    for value, count in rows:
        print(f"{value}: {count}")


all_local = find_local_imports("core") + find_local_imports("apps")
files_counter = Counter(str(item["file"]) for item in all_local)
module_counter = Counter(str(item["module"]) for item in all_local)

print(f"Total local imports: {len(all_local)}")
_print_counter("Top 20 files with most local imports:", files_counter.most_common(20))
_print_counter("Top 20 most locally imported modules:", module_counter.most_common(20))
