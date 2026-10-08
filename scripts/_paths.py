"""Sibling-резолюция исходников UI при миграции JS -> TS.

Правила: hard cutover — каноничный путь один; если `<name>.js` отсутствует,
а рядом есть `<name>.ts`, используется `.ts`. Сканеры обязаны видеть оба
суффикса (`*.{js,ts}`).
"""

from pathlib import Path


def js_or_ts(path: Path) -> Path:
    """Путь к исходнику: `.ts`-sibling при наличии, иначе исходный `.js`."""
    if path.suffix == ".js":
        ts = path.with_suffix(".ts")
        if ts.is_file():
            return ts
    return path


def iter_ui_sources(root: Path) -> list[Path]:
    """Все UI-исходники каталога: `.js` + `.ts`."""
    if not root.is_dir():
        return []
    out: list[Path] = []
    for pattern in ("*.js", "*.ts"):
        out.extend(root.rglob(pattern))
    return sorted(set(out))
