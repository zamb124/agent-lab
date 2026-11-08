"""Оптимизация маркетинговых кадров в land/optimized/ через sips.

``python -m scripts.tools.land_optimize [--src DIR] [--width 2400]``

Исходники — ``tests/ui/shots/out`` (2x PNG ~2880px) или ``apps/frontend/
ui/assets/images/land``; результат — JPEG-подобные PNG в ``optimized/``
шириной ``--width`` (default 2400 — retina для 1200px-слотов).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = REPO_ROOT / "tests/ui/shots/out"
OPTIMIZED_DIR = (
    REPO_ROOT / "apps/frontend/ui/assets/images/land/optimized"
)


def optimize(src_dir: Path, width: int, pattern: str) -> list[Path]:
    OPTIMIZED_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for src in sorted(src_dir.glob(pattern)):
        dst = OPTIMIZED_DIR / src.name
        proc = subprocess.run(
            ["sips", "-Z", str(width), "-s", "format", "png",
             str(src), "--out", str(dst)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print(f"FAIL {src.name}: {proc.stderr.strip()}", file=sys.stderr)
            continue
        written.append(dst)
        print(f"OK   {src.name} -> optimized/{dst.name}")
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--width", type=int, default=2400)
    parser.add_argument("--pattern", default="*.png")
    args = parser.parse_args()
    if not args.src.is_dir():
        print(f"src dir не найден: {args.src}", file=sys.stderr)
        raise SystemExit(1)
    written = optimize(args.src, args.width, args.pattern)
    print(f"\n{len(written)} файлов -> {OPTIMIZED_DIR}")


if __name__ == "__main__":
    main()
