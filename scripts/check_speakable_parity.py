"""CI: паритет whitelist SPEAKABLE между apps/flows/src/streaming/speakable.py и JS."""

from __future__ import annotations

import ast
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
PY_PATH = ROOT / "apps" / "flows" / "src" / "streaming" / "speakable.py"
JS_PATH = ROOT / "core" / "frontend" / "static" / "lib" / "voice" / "speakable.js"


def _artifact_names_from_python(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        target_name: str | None = None
        value_node: ast.expr | None = None
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    target_name = target.id
                    value_node = node.value
                    break
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            value_node = node.value
        else:
            continue
        if target_name != "SPEAKABLE_ARTIFACT_NAMES" or value_node is None:
            continue
        elt = value_node
        if isinstance(elt, ast.Call) and elt.args:
            inner = elt.args[0]
            if isinstance(inner, ast.Set):
                out: set[str] = set()
                for item in inner.elts:
                    if isinstance(item, ast.Constant) and isinstance(item.value, str):
                        out.add(item.value)
                return out
        raise RuntimeError(
            f"SPEAKABLE_ARTIFACT_NAMES unsupported initializer shape in {path}"
        )
    raise RuntimeError(f"SPEAKABLE_ARTIFACT_NAMES not found in {path}")


def _artifact_names_from_js(path: pathlib.Path) -> set[str]:
    raw = path.read_text(encoding="utf-8")
    match = re.search(
        r"SPEAKABLE_ARTIFACT_NAMES\s*=\s*Object\.freeze\(new\s+Set\(\[([\s\S]*?)\]\)\)",
        raw,
    )
    if match is None:
        raise RuntimeError(f"SPEAKABLE_ARTIFACT_NAMES Set not found in {path}")
    body = match.group(1)
    strings = re.findall(r"'([^'\\]*)'|\"([^\"\\]*)\"", body)
    names: set[str] = set()
    for a, b in strings:
        name = a if a else b
        if name != "":
            names.add(name)
    return names


def main() -> int:
    py_names = _artifact_names_from_python(PY_PATH)
    js_names = _artifact_names_from_js(JS_PATH)
    if py_names != js_names:
        only_py = sorted(py_names - js_names)
        only_js = sorted(js_names - py_names)
        print(
            "speakable parity failed:\n"
            f"  python only: {only_py}\n"
            f"  js only:     {only_js}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
