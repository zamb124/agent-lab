"""S3-клиент и aioboto3 живут только в core/files/object_store."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = ROOT / "core" / "files" / "object_store"
SCAN = (ROOT / "core", ROOT / "apps")
NEEDLES = ("S3ClientFactory", "import aioboto3", "from aioboto3")


def main() -> int:
    violations: list[str] = []
    for base in SCAN:
        for path in base.rglob("*.py"):
            if ALLOWED in path.parents or path == ALLOWED:
                continue
            text = path.read_text(encoding="utf-8")
            for needle in NEEDLES:
                if needle in text:
                    violations.append(f"{path.relative_to(ROOT)}: {needle}")
    if violations:
        print("object store canon: S3 client leaked outside core/files/object_store", file=sys.stderr)
        for line in violations:
            print(line, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
